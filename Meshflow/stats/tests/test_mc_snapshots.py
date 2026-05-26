"""Tests for MeshCore stats snapshot collectors (#329)."""

from datetime import datetime

from django.utils import timezone

import pytest

from common.protocol import Protocol
from meshcore_packets.models import MeshCorePayloadType, MeshCorePacketObservation, MeshCoreRawPacket
from stats.models import StatsSnapshot
from stats.tasks import (
    _collect_mc_online_nodes,
    _collect_mc_packet_volume,
    _collect_mc_new_nodes,
    _collect_online_nodes,
)


@pytest.mark.django_db
def test_mt_online_nodes_excludes_meshcore_observed_node(create_observed_node):
    """#365: MC ObservedNode must not count toward online_nodes."""
    hour = timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0))
    mc_node = create_observed_node(
        meshtastic_node_id=None,
        protocol=Protocol.MESHCORE,
        mc_pubkey="b" * 64,
    )
    mc_node.last_heard = timezone.make_aware(datetime(2025, 3, 15, 11, 30, 0))
    mc_node.save()

    mt_node = create_observed_node(meshtastic_node_id=222222222)
    mt_node.last_heard = timezone.make_aware(datetime(2025, 3, 15, 11, 30, 0))
    mt_node.save()

    _collect_online_nodes(hour, run_id=None)

    snap = StatsSnapshot.objects.get(stat_type="online_nodes", constellation__isnull=True, recorded_at=hour)
    assert snap.value["count"] == 1


@pytest.mark.django_db
def test_mc_packet_volume_by_type(meshcore_feeder):
    """mc_packet_volume includes per payload_type breakdown."""
    hour = timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0))
    observer = meshcore_feeder["node"]

    MeshCoreRawPacket.objects.create(
        observer=observer,
        payload_type=MeshCorePayloadType.ADVERT,
        event_type="advertisement",
        from_pubkey="b" * 64,
        rx_time=hour,
        first_reported_time=hour,
        raw_json={},
    )
    MeshCoreRawPacket.objects.create(
        observer=observer,
        payload_type=MeshCorePayloadType.CHANNEL_TEXT,
        event_type="channel_text",
        from_pubkey="c" * 64,
        rx_time=hour,
        first_reported_time=hour,
        raw_json={},
    )

    _collect_mc_packet_volume(hour, run_id=None)

    snap = StatsSnapshot.objects.get(stat_type="mc_packet_volume", recorded_at=hour)
    assert snap.value["count"] == 2
    assert snap.value["by_type"]["advert"] == 1
    assert snap.value["by_type"]["channel_text"] == 1


@pytest.mark.django_db
def test_mc_online_nodes_global_and_constellation(meshcore_feeder, create_observed_node):
    """mc_online_nodes uses MC last_heard globally and observations per constellation."""
    hour = timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0))
    mc_node = create_observed_node(
        meshtastic_node_id=None,
        protocol=Protocol.MESHCORE,
        mc_pubkey="d" * 64,
    )
    mc_node.last_heard = timezone.make_aware(datetime(2025, 3, 15, 11, 30, 0))
    mc_node.save()

    observer = meshcore_feeder["node"]
    packet = MeshCoreRawPacket.objects.create(
        observer=observer,
        payload_type=MeshCorePayloadType.ADVERT,
        event_type="advertisement",
        from_pubkey="e" * 64,
        rx_time=timezone.make_aware(datetime(2025, 3, 15, 11, 45, 0)),
        first_reported_time=timezone.make_aware(datetime(2025, 3, 15, 11, 45, 0)),
        raw_json={},
    )
    MeshCorePacketObservation.objects.create(
        packet=packet,
        observer=observer,
        rx_time=timezone.make_aware(datetime(2025, 3, 15, 11, 45, 0)),
    )

    _collect_mc_online_nodes(hour, run_id=None)

    global_snap = StatsSnapshot.objects.get(
        stat_type="mc_online_nodes", constellation__isnull=True, recorded_at=hour
    )
    assert global_snap.value["count"] == 1

    const_snap = StatsSnapshot.objects.get(
        stat_type="mc_online_nodes",
        constellation=observer.constellation,
        recorded_at=hour,
    )
    assert const_snap.value["count"] == 1


@pytest.mark.django_db
def test_mc_new_nodes_backfill_hour_window(meshcore_feeder, create_observed_node):
    """mc_new_nodes backfill counts nodes created in the hour window."""
    hour = timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0))
    node = create_observed_node(
        meshtastic_node_id=None,
        protocol=Protocol.MESHCORE,
        mc_pubkey="f" * 64,
    )
    node.created_at = timezone.make_aware(datetime(2025, 3, 15, 12, 15, 0))
    node.save(update_fields=["created_at"])

    _collect_mc_new_nodes(hour, run_id=None, for_backfill=True)

    snap = StatsSnapshot.objects.get(stat_type="mc_new_nodes", constellation__isnull=True, recorded_at=hour)
    assert snap.value["count"] == 1
