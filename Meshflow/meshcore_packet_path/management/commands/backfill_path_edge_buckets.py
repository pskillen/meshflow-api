"""Backfill passive path edge buckets for past hours."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from meshcore_packet_path.services.rollup import (
    collect_path_edge_buckets_for_range,
    resolve_backfill_hours,
)


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
        try:
            hours = resolve_backfill_hours(hours=options.get("hours"), days=options.get("days"))
        except ValueError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
        start_hour = current_hour - timedelta(hours=hours)
        self.stdout.write(
            f"Backfilling path edge buckets for {hours} hour(s) " f"from {start_hour} to {current_hour}..."
        )
        result = collect_path_edge_buckets_for_range(
            start_hour,
            current_hour,
            skip_existing=True,
            show_progress=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: created={result['created']}, updated={result['updated']}, "
                f"skipped_hours={result['skipped_hours']}, "
                f"observations_processed={result['observations_processed']}"
            )
        )
