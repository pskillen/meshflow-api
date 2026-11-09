"""Backfill daily node_firmware snapshots. Idempotent; run after backfill_inferred_firmware."""

from django.core.management.base import BaseCommand, CommandError

from stats.tasks import backfill_node_firmware_snapshots


class Command(BaseCommand):
    help = "Backfill daily node_firmware snapshots for the last N days (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90, help="Number of days to backfill (default: 90)")
        parser.add_argument("--dry-run", action="store_true", help="Count what would be created; write nothing")

    def handle(self, *args, **options):
        if options["days"] < 1:
            raise CommandError("--days must be at least 1")
        prefix = "[dry-run] " if options["dry_run"] else ""
        result = backfill_node_firmware_snapshots(days=options["days"], dry_run=options["dry_run"])
        self.stdout.write(f"{prefix}Scanned {result['scanned']} day/node rows in {result['scan_seconds']:.1f} seconds")
        self.stdout.write(f"{prefix}Snapshots: created {result['created']}, already present {result['skipped']}")
