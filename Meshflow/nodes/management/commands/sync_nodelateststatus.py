"""
Management command to re-sync NodeLatestStatus from Position and DeviceMetrics tables.

Repairs any stale NodeLatestStatus records by copying the latest Position and
DeviceMetrics for each ObservedNode. Idempotent — safe to run whenever necessary.
"""

from django.core.management.base import BaseCommand

from tqdm import tqdm

from nodes.models import DeviceMetrics, NodeLatestStatus, ObservedNode, Position


class Command(BaseCommand):
    help = "Re-sync NodeLatestStatus from Position and DeviceMetrics tables (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes will be made"))

        # Get all ObservedNodes that have at least one Position or DeviceMetrics
        nodes_with_position = set(Position.objects.values_list("node_id", flat=True).distinct())
        nodes_with_metrics = set(DeviceMetrics.objects.values_list("node_id", flat=True).distinct())
        node_ids = nodes_with_position | nodes_with_metrics

        nodes = ObservedNode.objects.filter(internal_id__in=node_ids).order_by("node_id")
        total = nodes.count()

        if total == 0:
            self.stdout.write("No nodes with Position or DeviceMetrics found")
            return

        updated = 0
        created = 0

        for node in tqdm(nodes, desc="Syncing NodeLatestStatus", unit="node"):
            defaults = {}

            # Sync from latest Position
            latest_pos = Position.objects.filter(node=node).order_by("-reported_time").first()
            if latest_pos:
                defaults.update(
                    latitude=latest_pos.latitude,
                    longitude=latest_pos.longitude,
                    altitude=latest_pos.altitude,
                    heading=latest_pos.heading,
                    location_source=latest_pos.location_source,
                    precision_bits=latest_pos.precision_bits,
                    ground_speed=latest_pos.ground_speed,
                    ground_track=latest_pos.ground_track,
                    position_reported_time=latest_pos.reported_time,
                )

            # Sync from latest DeviceMetrics
            latest_metrics = DeviceMetrics.objects.filter(node=node).order_by("-reported_time").first()
            if latest_metrics:
                defaults.update(
                    battery_level=latest_metrics.battery_level,
                    voltage=latest_metrics.voltage,
                    channel_utilization=latest_metrics.channel_utilization,
                    air_util_tx=latest_metrics.air_util_tx,
                    uptime_seconds=latest_metrics.uptime_seconds,
                    metrics_reported_time=latest_metrics.reported_time,
                )

            if not defaults:
                continue

            if dry_run:
                updated += 1
                continue

            _, was_created = NodeLatestStatus.objects.update_or_create(
                node=node,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Would update {updated} NodeLatestStatus records"))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Synced {updated + created} nodes ({created} created, {updated} updated)")
            )
