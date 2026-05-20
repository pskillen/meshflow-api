"""Unit tests for MeshCore ADVERT position ingest."""

from datetime import datetime
from datetime import timezone as dt_timezone

from django.utils import timezone

import pytest

from common.protocol import Protocol
from meshcore_packets.models import MeshCorePayloadType
from meshcore_packets.services.position import (
    adv_timestamp_to_aware,
    apply_advert_position,
    extract_adv_coords,
)
from nodes.models import MeshCoreLocationSource, NodeLatestStatus, ObservedNode, Position


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"adv_lat": 55.1, "adv_lon": -4.2}, (55.1, -4.2)),
        ({"adv_lat": 0.0, "adv_lon": 10.5}, (0.0, 10.5)),
        ({"adv_lat": 0.0, "adv_lon": 0.0}, None),
        ({}, None),
        ({"adv_lat": 1.0}, None),
    ],
)
def test_extract_adv_coords(raw, expected):
    assert extract_adv_coords(raw) == expected


def test_adv_timestamp_to_aware():
    ts = 1778102274
    result = adv_timestamp_to_aware({"adv_timestamp": ts})
    assert result == datetime.fromtimestamp(ts, tz=dt_timezone.utc)


@pytest.mark.django_db
def test_apply_advert_position_creates_position_and_nls(meshcore_feeder):
    now = timezone.now()
    node = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="a" * 64,
        long_name="",
        short_name="",
        last_heard=now,
    )
    from meshcore_packets.models import MeshCoreRawPacket

    packet = MeshCoreRawPacket.objects.create(
        observer=meshcore_feeder["node"],
        payload_type=MeshCorePayloadType.ADVERT,
        event_type="rx_log_data",
        from_pubkey="a" * 64,
        pkt_hash=42,
        rx_time=now,
        raw_json={"adv_lat": 55.1, "adv_lon": -4.2, "adv_timestamp": int(now.timestamp())},
    )

    assert apply_advert_position(node=node, packet=packet, raw=packet.raw_json) is True
    assert Position.objects.filter(node=node).count() == 1
    position = Position.objects.get(node=node)
    assert position.latitude == 55.1
    assert position.longitude == -4.2
    assert position.meshcore_location_source == MeshCoreLocationSource.ADVERT
    assert position.original_mc_packet_id == packet.id

    status = NodeLatestStatus.objects.get(node=node)
    assert status.latitude == 55.1
    assert status.longitude == -4.2
    assert status.meshcore_location_source == MeshCoreLocationSource.ADVERT
    assert status.position_reported_time is not None


@pytest.mark.django_db
def test_apply_advert_position_absent_coords_no_row(meshcore_feeder):
    now = timezone.now()
    node = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="c" * 64,
        long_name="",
        short_name="",
        last_heard=now,
    )
    from meshcore_packets.models import MeshCoreRawPacket

    packet = MeshCoreRawPacket.objects.create(
        observer=meshcore_feeder["node"],
        payload_type=MeshCorePayloadType.ADVERT,
        event_type="rx_log_data",
        from_pubkey="c" * 64,
        pkt_hash=43,
        rx_time=now,
        raw_json={"adv_lat": 0.0, "adv_lon": 0.0},
    )

    assert apply_advert_position(node=node, packet=packet, raw=packet.raw_json) is False
    assert Position.objects.filter(node=node).count() == 0
    assert not NodeLatestStatus.objects.filter(node=node).exists()
