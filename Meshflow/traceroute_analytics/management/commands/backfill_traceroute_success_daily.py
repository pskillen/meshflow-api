"""
Management command to backfill tr_success_daily snapshots for past days.

Runs the Celery task synchronously. Idempotent: skips days that already have snapshots.
"""

from django.core.management.base import BaseCommand

from traceroute.tasks import backfill_traceroute_success_daily


class Command(BaseCommand):
    help = "Backfill tr_success_daily snapshots for the last N days (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to backfill (default: 30)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        self.stdout.write(f"Backfilling traceroute success daily for the last {days} days...")
        result = backfill_traceroute_success_daily.apply(kwargs={"days": days})
        data = result.get()
        self.stdout.write(
            self.style.SUCCESS(f"Done: created={data['created']}, skipped={data['skipped']}, days={data['days']}")
        )
