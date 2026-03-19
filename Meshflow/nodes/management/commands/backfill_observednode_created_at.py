"""
Backfill ObservedNode.created_at from earliest RawPacket.first_reported_time per from_int.

Same logic as migration nodes.0026_backfill_observednode_created_at. Use when the migration
did not run, failed partway, or data was later imported with incorrect created_at values.
"""

from django.core.management.base import BaseCommand
from django.db.models import Min

from tqdm import tqdm

from nodes.models import ObservedNode
from packets.models import RawPacket


class Command(BaseCommand):
    help = (
        "Set ObservedNode.created_at from Min(RawPacket.first_reported_time) for each from_int / node_id. "
        "By default only rows with created_at IS NULL are updated (migration 0026 parity). "
        "Use --overwrite to refresh created_at from packet history for all matching nodes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many rows would be updated without writing",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Update all ObservedNodes that have RawPackets, not only created_at IS NULL",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        overwrite = options["overwrite"]

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no database writes"))

        earliest_rows = (
            RawPacket.objects.filter(from_int__isnull=False)
            .values("from_int")
            .annotate(earliest_time=Min("first_reported_time"))
        )

        total_candidates = earliest_rows.count()
        if total_candidates == 0:
            self.stdout.write("No RawPacket rows with from_int; nothing to do.")
            return

        would_update = 0
        updated = 0
        no_observed_node = 0

        iterator = earliest_rows.order_by().iterator(chunk_size=2000)
        if not dry_run:
            iterator = tqdm(iterator, total=total_candidates, unit="node", desc="Backfill created_at")

        for row in iterator:
            from_int = row["from_int"]
            earliest_time = row["earliest_time"]

            if not ObservedNode.objects.filter(node_id=from_int).exists():
                no_observed_node += 1
                continue

            qs = ObservedNode.objects.filter(node_id=from_int)
            if not overwrite:
                qs = qs.filter(created_at__isnull=True)

            if not qs.exists():
                continue

            if dry_run:
                would_update += qs.count()
            else:
                updated += qs.update(created_at=earliest_time)

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run: would update {would_update} ObservedNode row(s). "
                    f"{no_observed_node} from_int value(s) had no ObservedNode."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated {updated} ObservedNode row(s). "
                    f"({no_observed_node} from_int value(s) had no ObservedNode.)"
                )
            )
