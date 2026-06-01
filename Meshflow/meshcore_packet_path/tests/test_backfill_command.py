"""Management command tests."""

from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone

import pytest

from meshcore_packet_path.models import MeshCorePathEdgeBucket
from meshcore_packet_path.services.rollup import resolve_backfill_hours


def test_resolve_backfill_hours_days_and_hours():
    assert resolve_backfill_hours(days=7) == 7 * 24
    assert resolve_backfill_hours(hours=12) == 12
    assert resolve_backfill_hours() == 24
    with pytest.raises(ValueError):
        resolve_backfill_hours(hours=1, days=1)


@pytest.mark.django_db
def test_backfill_command_creates_buckets(path_observation):
    obs = path_observation["observation"]
    current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    obs.upload_time = current_hour - timedelta(hours=1)
    obs.save(update_fields=["upload_time"])

    call_command("backfill_path_edge_buckets", hours=1)
    assert MeshCorePathEdgeBucket.objects.exists()

    call_command("backfill_path_edge_buckets", hours=1)
    assert MeshCorePathEdgeBucket.objects.filter(bucket_start=obs.upload_time).count() == 2


@pytest.mark.django_db
def test_backfill_command_accepts_days(path_observation):
    obs = path_observation["observation"]
    current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    obs.upload_time = current_hour - timedelta(hours=1)
    obs.save(update_fields=["upload_time"])

    call_command("backfill_path_edge_buckets", days=1)
    assert MeshCorePathEdgeBucket.objects.exists()
