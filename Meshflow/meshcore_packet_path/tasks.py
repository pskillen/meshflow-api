"""Celery tasks for MeshCore passive packet path rollups and retention."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from celery import shared_task

from meshcore_packet_path.services.rollup import (
    collect_path_edge_buckets_for_hour,
    collect_path_edge_buckets_for_range,
    resolve_backfill_hours,
)


@shared_task(ignore_result=True)
def collect_path_edge_buckets():
    """Hourly: rollup hash-chain edges for the completed previous hour."""
    current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    hour_start = current_hour - timedelta(hours=1)
    return collect_path_edge_buckets_for_hour(hour_start)


@shared_task
def backfill_path_edge_buckets_task(hours: int | None = None, days: int | None = None) -> dict:
    """
    Backfill rollups for the last N hours or days (idempotent when skip_existing=True).

    Prefer ``python manage.py backfill_path_edge_buckets`` for CLI use (--hours / --days).
    """
    backfill_hours = resolve_backfill_hours(hours=hours, days=days)
    current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    start_hour = current_hour - timedelta(hours=backfill_hours)
    return collect_path_edge_buckets_for_range(start_hour, current_hour, skip_existing=True)


@shared_task(ignore_result=True)
def evict_old_path_data():
    """Delete path edge buckets (and stale unknown segments) older than retention."""
    from meshcore_packet_path.models import MeshCorePathEdgeBucket, MeshCorePathSegmentResolution, SegmentStatus

    days = int(getattr(settings, "MESHCORE_PATH_RETENTION_DAYS", 183))
    cutoff = timezone.now() - timedelta(days=days)

    buckets_deleted, _ = MeshCorePathEdgeBucket.objects.filter(bucket_start__lt=cutoff).delete()
    segments_deleted, _ = MeshCorePathSegmentResolution.objects.filter(
        last_seen_at__lt=cutoff,
        status=SegmentStatus.UNKNOWN,
        source="",
    ).delete()

    return {
        "buckets_deleted": buckets_deleted,
        "segments_deleted": segments_deleted,
        "cutoff": cutoff.isoformat(),
    }
