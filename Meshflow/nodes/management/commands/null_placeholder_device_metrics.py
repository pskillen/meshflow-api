"""
Null placeholder zero device metrics stored before ingestion kept missing readings as null.

Before null ingestion a missing reading was stored as 0. This command nulls the obvious placeholders in
``DeviceMetrics`` and then ``NodeLatestStatus``. Rules (every one is evaluated against the row as stored):

* channel utilisation and air util TX: both 0 and battery, voltage and uptime also 0 (an all-zero NodeDB
  placeholder row). Otherwise a 0 is a real reading and is kept;
* battery: 0 and voltage is 0 or null (a flat battery still reports volts);
* voltage: 0;
* uptime: 0.

``--dry-run`` writes nothing and prints what a real run would change. Idempotent: a second run changes no
rows. ``--before`` limits it to rows reported before a cut-over time (pass the null-ingestion deploy time):
``DeviceMetrics.logged_time`` and ``NodeLatestStatus.metrics_reported_time``. Each batch is one id-range
``.update()`` in its own transaction (every field set with a ``CASE``, so a row is rewritten once); the
counts come from one conditional ``aggregate`` per batch, taken before the update, in dry-run and real runs alike.
"""

from functools import reduce
from operator import or_

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Case, Count, F, Max, Min, Q, Value, When
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive, make_aware

from nodes.models import DeviceMetrics, NodeLatestStatus

_ALL_ZERO = Q(
    meshtastic_channel_utilization=0,
    meshtastic_air_util_tx=0,
    battery_level=0,
    voltage=0,
    uptime_seconds=0,
)

# (rule label, filter, fields to null). Every filter is evaluated on the stored row, and the battery rule treats
# null and 0 voltage alike, so earlier nulling never changes a later match (dry-run counts equal real counts).
RULES = [
    ("channel/air util (all-zero row)", _ALL_ZERO, ["meshtastic_channel_utilization", "meshtastic_air_util_tx"]),
    (
        "battery_level (0 with 0/null voltage)",
        Q(battery_level=0) & (Q(voltage=0) | Q(voltage__isnull=True)),
        ["battery_level"],
    ),
    ("voltage (0)", Q(voltage=0), ["voltage"]),
    ("uptime_seconds (0)", Q(uptime_seconds=0), ["uptime_seconds"]),
]


def _field_conditions():
    """For each field some rule nulls, the OR of the filters of the rules that null it."""
    conditions = {}
    for _, condition, fields in RULES:
        for field in fields:
            conditions[field] = conditions[field] | condition if field in conditions else condition
    return conditions


FIELD_CONDITIONS = _field_conditions()
# Only rows some rule matches are rewritten; the CASE leaves their other fields as they were.
ANY_RULE = reduce(or_, (condition for _, condition, _ in RULES))

# (model, field used by --before)
TARGETS = [(DeviceMetrics, "logged_time"), (NodeLatestStatus, "metrics_reported_time")]


class Command(BaseCommand):
    help = "Null placeholder zero device metrics (DeviceMetrics, then NodeLatestStatus). Use --dry-run first."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing")
        parser.add_argument("--batch-size", type=int, default=5000, help="Id range per transaction (default 5000)")
        parser.add_argument(
            "--before",
            help="ISO datetime: only rows reported before this (pass the null-ingestion deploy time; an old cutoff "
            "matching few rows scans most of the table to find its id range)",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1")
        dry_run = options["dry_run"]
        before = None
        if options["before"]:
            try:
                before = parse_datetime(options["before"])
            except ValueError:
                before = None
            if before is None:
                raise CommandError("--before must be an ISO datetime, e.g. 2026-11-10T12:00:00Z")
            if is_naive(before):
                before = make_aware(before)

        prefix = "[dry-run] " if dry_run else ""
        for model, time_field in TARGETS:
            base = model.objects.all()
            if before is not None:
                base = base.filter(**{f"{time_field}__lt": before})
            bounds = base.aggregate(lo=Min("id"), hi=Max("id"))
            counts = {label: 0 for label, _, _ in RULES}
            if bounds["lo"] is not None:
                for start in range(bounds["lo"], bounds["hi"] + 1, batch_size):
                    window = base.filter(id__gte=start, id__lt=start + batch_size)
                    with transaction.atomic():
                        found = window.aggregate(
                            **{f"r{i}": Count("id", filter=cond) for i, (_, cond, _) in enumerate(RULES)}
                        )
                        for i, (label, _, _) in enumerate(RULES):
                            counts[label] += found[f"r{i}"]
                        if not dry_run:
                            window.filter(ANY_RULE).update(
                                **{
                                    field: Case(
                                        When(cond, then=Value(None)),
                                        default=F(field),
                                        output_field=model._meta.get_field(field),
                                    )
                                    for field, cond in FIELD_CONDITIONS.items()
                                }
                            )
            self.stdout.write(f"{prefix}{model.__name__}:")
            for label, n in counts.items():
                self.stdout.write(f"  {label}: {n}")
