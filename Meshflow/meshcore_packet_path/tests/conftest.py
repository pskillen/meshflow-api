"""Shared fixtures for meshcore_packet_path tests."""

from django.utils import timezone

import pytest

from meshcore_packets.models import MeshCorePacketObservation, MeshCorePayloadType, MeshCoreRawPacket


@pytest.fixture
def path_observation(meshcore_feeder):
    """Observation with a two-hop path for rollup tests."""
    now = timezone.now().replace(minute=0, second=0, microsecond=0)
    packet = MeshCoreRawPacket.objects.create(
        observer=meshcore_feeder["node"],
        payload_type=MeshCorePayloadType.CHANNEL_TEXT,
        event_type="channel_message",
        rx_time=now,
        raw_json={},
    )
    obs = MeshCorePacketObservation.objects.create(
        packet=packet,
        observer=meshcore_feeder["node"],
        rx_time=now,
        upload_time=now,
        path_hashes=["aa", "bb", "cc"],
        path_hash_size=1,
        path_hash_mode=2,
        rx_snr=-5.0,
    )
    return {"packet": packet, "observation": obs, "hour_start": now}
