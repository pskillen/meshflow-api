"""
Management command to backfill stats snapshots (online_nodes, packet_volume) for past days.

Runs the Celery task synchronously. Idempotent: skips hours that already have snapshots.

With --rewrite-online it instead recomputes the count on existing online_nodes / mc_online_nodes rows
from raw packets (the bounded 2h window, api#501) and never inserts rows.
"""

from django.core.management.base import BaseCommand

from stats.tasks import backfill_stats_snapshots, rewrite_online_node_snapshots


class Command(BaseCommand):
    help = "Backfill online_nodes and packet_volume snapshots for the last N days (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to backfill (default: 30)",
        )
        parser.add_argument(
            "--rewrite-online",
            action="store_true",
            help=(
                "Instead of inserting missing hours, recompute the count on existing online_nodes and "
                "mc_online_nodes rows from raw packets. Never inserts rows; rows whose window has no "
                "raw packets are left alone. Idempotent."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="With --rewrite-online: report what would change without saving.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if options["rewrite_online"]:
            self.stdout.write(f"Rewriting online snapshot counts for the last {days} days...")
            data = rewrite_online_node_snapshots.apply(kwargs={"days": days, "dry_run": options["dry_run"]}).get()
            verb = "would rewrite" if data["dry_run"] else "rewritten"
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done: {verb}={data['rewritten']}, unchanged={data['unchanged']}, "
                    f"left_alone_no_raw_packets={data['no_raw_packets']}"
                )
            )
            self.stdout.write(f"Earliest corrected hour: {data['earliest_corrected']}")
            self.stdout.write(f"Earliest row with raw packets in its window: {data['earliest_with_raw_packets']}")
            return

        self.stdout.write(f"Backfilling stats snapshots for the last {days} days...")
        result = backfill_stats_snapshots.apply(kwargs={"days": days})
        data = result.get()
        self.stdout.write(
            self.style.SUCCESS(f"Done: created={data['created']}, skipped={data['skipped']}, days={data['days']}")
        )
