"""Management command tests."""

from django.core.management import call_command
from django.utils import timezone

import pytest

from meshcore_packet_path.models import MeshCorePathEdgeBucket


@pytest.mark.django_db
def test_backfill_command_creates_buckets(path_observation):
    from datetime import timedelta

    obs = path_observation["observation"]
    current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    obs.upload_time = current_hour - timedelta(hours=1)
    obs.save(update_fields=["upload_time"])

    call_command("backfill_path_edge_buckets", hours=1)
    assert MeshCorePathEdgeBucket.objects.exists()

    call_command("backfill_path_edge_buckets", hours=1)
    assert MeshCorePathEdgeBucket.objects.filter(bucket_start=obs.upload_time).count() == 2
