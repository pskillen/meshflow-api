"""Backfill passive path edge buckets for past hours."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from meshcore_packet_path.services.rollup import collect_path_edge_buckets_for_range


class Command(BaseCommand):
    help = "Backfill MeshCore path edge buckets for the last N hours or days (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=None,
            help="Number of hours to backfill (default: use --days or 24)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Number of days to backfill",
        )

    def handle(self, *args, **options):
        hours = options.get("hours")
        days = options.get("days")
        if days is not None:
            hours = days * 24
        if hours is None:
            hours = 24

        current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
        start_hour = current_hour - timedelta(hours=hours)
        self.stdout.write(f"Backfilling path edge buckets from {start_hour} to {current_hour}...")
        result = collect_path_edge_buckets_for_range(
            start_hour,
            current_hour,
            skip_existing=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: created={result['created']}, updated={result['updated']}, "
                f"skipped_hours={result['skipped_hours']}, "
                f"observations_processed={result['observations_processed']}"
            )
        )
