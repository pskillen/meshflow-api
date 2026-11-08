"""Merge duplicate Meshtastic ObservedNode rows (same node number) into the oldest row.

Idempotent and batched. Safe to re-run; ``--dry-run`` writes nothing and prints the numbers a real run would write.
Back up the database first. The merge rules live in ``nodes.services.observed_node_merge``.
"""

from django.core.management.base import BaseCommand

from nodes.services.observed_node_merge import merge_duplicate_meshtastic_nodes


class Command(BaseCommand):
    help = (
        "Merge ObservedNode rows that share a Meshtastic node number into the oldest row, re-pointing every related "
        "row at it. Sets whose rows have different claimed_by owners are skipped and reported."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing.")
        parser.add_argument("--batch-size", type=int, default=500, help="Node numbers per batch (default 500).")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        prefix = "[dry-run] " if dry_run else ""
        report = merge_duplicate_meshtastic_nodes(dry_run=dry_run, batch_size=options["batch_size"])

        self.stdout.write(
            f"{prefix}Duplicate sets found: {report.sets_found}, merged: {report.sets_merged}, "
            f"rows merged away: {report.rows_merged}, conflicts skipped: {report.conflicts_skipped}"
        )
        for relation, count in sorted(report.moved.items()):
            self.stdout.write(f"{prefix}  moved {count} {relation}")
        for relation, count in sorted(report.dropped.items()):
            self.stdout.write(f"{prefix}  dropped {count} {relation} (clashed with the keeper's row)")
        for conflict in report.conflicts:
            self.stdout.write(self.style.WARNING(f"{prefix}  conflict, skipped: {conflict}"))
