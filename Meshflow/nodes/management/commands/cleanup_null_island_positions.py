"""
Remove 0,0 ("null island") positions stored before ingest started rejecting them.

Fixed-position nodes on Meshtastic 2.7.24-2.7.26 broadcast 0,0. Ingest now stores such packets with null
coordinates and no Position row; this command cleans up what was stored earlier:

* deletes ``nodes.Position`` rows at 0,0;
* for each NodeLatestStatus that currently holds 0,0, restores the position fields from the node's newest
  remaining Position, or nulls them when there is none;
* nulls latitude/longitude on 0,0 ``PositionPacket`` rows (the rows stay).

Dry-run by default; ``--apply`` writes. Idempotent. Each batch is its own transaction.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from common.geo import NULL_ISLAND_EPSILON
from nodes.models import NodeLatestStatus, Position
from packets.models import PositionPacket

# Position fields mirrored onto NodeLatestStatus (Position name -> status name).
_STATUS_FROM_POSITION = {
    "latitude": "latitude",
    "longitude": "longitude",
    "altitude": "altitude",
    "heading": "heading",
    "meshtastic_location_source": "meshtastic_location_source",
    "meshcore_location_source": "meshcore_location_source",
    "meshtastic_precision_bits": "meshtastic_precision_bits",
    "ground_speed": "ground_speed",
    "ground_track": "ground_track",
    "sats_in_view": "sats_in_view",
    "pdop": "pdop",
    "reported_time": "position_reported_time",
}


def _at_null_island():
    """Filter kwargs for rows at 0,0 (strict, matching common.geo.is_null_island)."""
    eps = NULL_ISLAND_EPSILON
    return {
        "latitude__gt": -eps,
        "latitude__lt": eps,
        "longitude__gt": -eps,
        "longitude__lt": eps,
    }


class Command(BaseCommand):
    help = (
        "Delete 0,0 Position rows, repair NodeLatestStatus positions that hold 0,0, and null 0,0 coordinates on "
        "PositionPacket rows. Dry-run unless --apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write changes (default is a dry run)")
        parser.add_argument("--batch-size", type=int, default=500, help="Rows per transaction (default 500)")

    def handle(self, *args, **options):
        apply = options["apply"]
        batch_size = max(1, options["batch_size"])

        if not apply:
            self.stdout.write(self.style.WARNING("Dry run: no database writes (use --apply)"))

        statuses_restored, statuses_nulled = self._fix_statuses(apply, batch_size)
        positions = self._delete_positions(apply, batch_size)
        packets = self._null_packets(apply, batch_size)

        verb = "" if apply else "would be "
        self.stdout.write(f"Position rows at 0,0 {verb}deleted: {positions}")
        self.stdout.write(
            f"NodeLatestStatus rows at 0,0 {verb}repaired: {statuses_restored + statuses_nulled} "
            f"({statuses_restored} restored from latest valid Position, {statuses_nulled} nulled)"
        )
        self.stdout.write(f"PositionPacket rows at 0,0 {verb}nulled: {packets}")

    def _fix_statuses(self, apply, batch_size):
        """Repair statuses at 0,0. Done before the delete so a crash between steps leaves nothing stale."""
        qs = NodeLatestStatus.objects.filter(**_at_null_island())
        restored = nulled = 0
        last_pk = 0
        while True:
            batch = list(qs.filter(pk__gt=last_pk).order_by("pk")[:batch_size])
            if not batch:
                break
            last_pk = batch[-1].pk
            with transaction.atomic():
                for status in batch:
                    newest = self._newest_valid_position(status.node_id)
                    if newest is not None:
                        restored += 1
                    else:
                        nulled += 1
                    if not apply:
                        continue
                    for pos_field, status_field in _STATUS_FROM_POSITION.items():
                        setattr(status, status_field, getattr(newest, pos_field) if newest is not None else None)
                    status.save(update_fields=list(_STATUS_FROM_POSITION.values()))
        return restored, nulled

    @staticmethod
    def _newest_valid_position(node_id):
        eps = NULL_ISLAND_EPSILON
        qs = Position.objects.filter(node_id=node_id, latitude__isnull=False, longitude__isnull=False)
        # Not null island: either axis is at least eps from zero.
        qs = qs.exclude(Q(latitude__gt=-eps, latitude__lt=eps) & Q(longitude__gt=-eps, longitude__lt=eps))
        return qs.order_by("-reported_time", "-pk").first()

    def _delete_positions(self, apply, batch_size):
        qs = Position.objects.filter(**_at_null_island())
        if not apply:
            return qs.count()
        total = 0
        while True:
            pks = list(qs.order_by("pk").values_list("pk", flat=True)[:batch_size])
            if not pks:
                break
            with transaction.atomic():
                total += Position.objects.filter(pk__in=pks).delete()[0]
        return total

    def _null_packets(self, apply, batch_size):
        qs = PositionPacket.objects.filter(**_at_null_island())
        if not apply:
            return qs.count()
        total = 0
        while True:
            pks = list(qs.order_by("pk").values_list("pk", flat=True)[:batch_size])
            if not pks:
                break
            with transaction.atomic():
                total += PositionPacket.objects.filter(pk__in=pks).update(latitude=None, longitude=None)
        return total
