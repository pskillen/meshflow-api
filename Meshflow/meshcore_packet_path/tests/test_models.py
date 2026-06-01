"""Model tests for meshcore_packet_path."""

from django.db import IntegrityError

import pytest

from meshcore_packet_path.models import MeshCorePathEdgeBucket, MeshCorePathSegmentResolution, SegmentStatus


@pytest.mark.django_db
def test_segment_resolution_unique_identity():
    MeshCorePathSegmentResolution.objects.create(
        segment_hash="f3bc",
        hash_size=2,
        hash_mode=1,
        status=SegmentStatus.UNKNOWN,
    )
    with pytest.raises(IntegrityError):
        MeshCorePathSegmentResolution.objects.create(
            segment_hash="f3bc",
            hash_size=2,
            hash_mode=1,
            status=SegmentStatus.UNKNOWN,
        )


@pytest.mark.django_db
def test_edge_bucket_update_or_create_idempotent(path_observation):
    hour = path_observation["hour_start"]
    observer = path_observation["observation"].observer
    defaults = {"packet_count": 1, "observation_count": 1}
    MeshCorePathEdgeBucket.objects.update_or_create(
        bucket_start=hour,
        bucket_size="1h",
        from_kind="hash",
        to_kind="hash",
        from_hash="aa",
        to_hash="bb",
        observer=observer,
        constellation_id=observer.constellation_id,
        defaults=defaults,
    )
    obj, created = MeshCorePathEdgeBucket.objects.update_or_create(
        bucket_start=hour,
        bucket_size="1h",
        from_kind="hash",
        to_kind="hash",
        from_hash="aa",
        to_hash="bb",
        observer=observer,
        constellation_id=observer.constellation_id,
        defaults={"packet_count": 9, "observation_count": 9},
    )
    assert created is False
    assert obj.packet_count == 9
    assert MeshCorePathEdgeBucket.objects.filter(bucket_start=hour, from_hash="aa").count() == 1
