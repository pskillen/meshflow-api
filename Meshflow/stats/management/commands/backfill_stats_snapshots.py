"""
Management command to backfill stats snapshots (online_nodes, packet_volume) for past days.

Runs the Celery task synchronously. Idempotent: skips hours that already have snapshots.
"""

from django.core.management.base import BaseCommand

from stats.tasks import backfill_stats_snapshots


class Command(BaseCommand):
    help = "Backfill online_nodes and packet_volume snapshots for the last N days (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to backfill (default: 30)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        self.stdout.write(f"Backfilling stats snapshots for the last {days} days...")
        result = backfill_stats_snapshots.apply(kwargs={"days": days})
        data = result.get()
        self.stdout.write(
            self.style.SUCCESS(f"Done: created={data['created']}, skipped={data['skipped']}, days={data['days']}")
        )
