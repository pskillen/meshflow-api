"""Rollup and eviction tests."""

from datetime import timedelta

from django.utils import timezone

import pytest

from meshcore_packet_path.models import MeshCorePathEdgeBucket, MeshCorePathSegmentResolution, SegmentStatus
from meshcore_packet_path.services.rollup import collect_path_edge_buckets_for_hour, touch_segment
from meshcore_packet_path.tasks import evict_old_path_data
from meshcore_packets.models import MeshCorePacketObservation, MeshCorePayloadType, MeshCoreRawPacket
from meshcore_packets.tests.conftest import FEEDER_B_MC_PUBKEY
from nodes.models import NodeAuth


@pytest.mark.django_db
def test_rollup_creates_hash_chain_edges(path_observation):
    hour = path_observation["hour_start"]
    result = collect_path_edge_buckets_for_hour(hour)
    assert result["observations_processed"] == 1
    assert MeshCorePathEdgeBucket.objects.filter(bucket_start=hour).count() == 2
    edges = set(MeshCorePathEdgeBucket.objects.filter(bucket_start=hour).values_list("from_hash", "to_hash"))
    assert edges == {("aa", "bb"), ("bb", "cc")}
    segments = MeshCorePathSegmentResolution.objects.filter(segment_hash__in=["aa", "bb", "cc"])
    assert segments.count() == 3
    assert all(s.status == SegmentStatus.UNKNOWN for s in segments)


@pytest.mark.django_db
def test_rollup_idempotent(path_observation):
    hour = path_observation["hour_start"]
    collect_path_edge_buckets_for_hour(hour)
    collect_path_edge_buckets_for_hour(hour)
    assert MeshCorePathEdgeBucket.objects.filter(bucket_start=hour).count() == 2


@pytest.mark.django_db
def test_rollup_two_feeders_distinct_edges(meshcore_feeder, create_managed_node, create_node_api_key):
    from common.protocol import Protocol

    hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    packet = MeshCoreRawPacket.objects.create(
        observer=meshcore_feeder["node"],
        payload_type=MeshCorePayloadType.ADVERT,
        event_type="advertisement",
        pkt_hash=88001,
        rx_time=hour,
        raw_json={},
    )
    feeder_b = create_managed_node(
        meshtastic_node_id=None,
        protocol=Protocol.MESHCORE,
        name="MC Feeder B",
        mc_pubkey=FEEDER_B_MC_PUBKEY,
    )
    api_key = create_node_api_key(constellation=feeder_b.constellation)
    NodeAuth.objects.create(api_key=api_key, node=feeder_b)

    MeshCorePacketObservation.objects.create(
        packet=packet,
        observer=meshcore_feeder["node"],
        rx_time=hour,
        upload_time=hour,
        path_hashes=["11", "22"],
    )
    MeshCorePacketObservation.objects.create(
        packet=packet,
        observer=feeder_b,
        rx_time=hour,
        upload_time=hour,
        path_hashes=["33", "44"],
    )

    collect_path_edge_buckets_for_hour(hour)
    assert MeshCorePathEdgeBucket.objects.filter(bucket_start=hour).count() == 2


@pytest.mark.django_db
def test_touch_segment_does_not_downgrade_manual(path_observation):
    seen = path_observation["hour_start"]
    seg = MeshCorePathSegmentResolution.objects.create(
        segment_hash="dead",
        hash_size=1,
        hash_mode=0,
        status=SegmentStatus.RESOLVED,
        source="manual_admin",
        first_seen_at=seen,
        last_seen_at=seen,
    )
    later = seen + timedelta(hours=1)
    touch_segment("dead", hash_size=1, hash_mode=0, seen_at=later)
    seg.refresh_from_db()
    assert seg.status == SegmentStatus.RESOLVED
    assert seg.source == "manual_admin"
    assert seg.last_seen_at == later


@pytest.mark.django_db
def test_eviction_respects_cutoff(path_observation, settings):
    settings.MESHCORE_PATH_RETENTION_DAYS = 30
    old = timezone.now() - timedelta(days=60)
    MeshCorePathEdgeBucket.objects.create(
        bucket_start=old,
        from_hash="x",
        to_hash="y",
    )
    MeshCorePathSegmentResolution.objects.create(
        segment_hash="oldseg",
        status=SegmentStatus.UNKNOWN,
        source="",
        first_seen_at=old,
        last_seen_at=old,
    )
    result = evict_old_path_data()
    assert result["buckets_deleted"] >= 1
    assert not MeshCorePathEdgeBucket.objects.filter(from_hash="x", to_hash="y").exists()
