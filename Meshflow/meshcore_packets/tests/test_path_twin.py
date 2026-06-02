"""Tests for rx_log → channel_text path twin merge."""

import json
from datetime import timedelta
from pathlib import Path

from django.utils import timezone

import pytest

from meshcore_packets.models import MeshCorePacketObservation, MeshCorePayloadType, MeshCoreTextPacket
from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.tests.conftest import FEEDER_MC_PUBKEY_PREFIX, feeder_url
from text_messages.models import TextMessage

DOCS = Path(__file__).resolve().parents[3] / "docs" / "packets" / "meshcore"
CHANNEL_MSG = DOCS / "channel_message" / "20260507_094921_075978.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


@pytest.fixture
def ingest_client(meshcore_feeder):
    from rest_framework.test import APIClient

    client = APIClient()
    client.credentials(HTTP_X_API_KEY=meshcore_feeder["api_key"].key)
    return client


@pytest.mark.django_db
def test_channel_text_then_raw_path_populates_text_observation(meshcore_feeder, ingest_client):
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    now = timezone.now()
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    channel_dump = _load(CHANNEL_MSG)
    text = channel_dump["payload"]["text"]
    rx_time = now.timestamp()

    r1 = ingest_client.post(
        url,
        {
            "event_type": "channel_message",
            "payload_type": "channel_text",
            "channel_idx": 0,
            "rx_time": rx_time,
            "text": text,
            "path_hash_mode": 2,
            "path_hash_size": 2,
            "raw": channel_dump,
        },
        format="json",
    )
    assert r1.status_code == 201
    text_packet = MeshCoreTextPacket.objects.get(text=text)
    text_obs = MeshCorePacketObservation.objects.get(packet=text_packet)
    assert not text_obs.path_hashes

    path_dump = json.loads((DOCS / "rx_log_data_path.json").read_text())
    r2 = ingest_client.post(
        url,
        {
            "event_type": "rx_log_data",
            "payload_type": "raw",
            "pkt_hash": path_dump["payload"]["pkt_hash"],
            "rx_time": rx_time,
            "path_hashes": ["f3bcf1"],
            "path_hash_size": 3,
            "path_hash_mode": path_dump["payload"].get("path_hash_mode"),
            "raw": path_dump,
        },
        format="json",
    )
    assert r2.status_code == 201
    text_obs.refresh_from_db()
    assert text_obs.path_hashes == ["f3bcf1"]
    assert text_obs.path_hash_size == 3

    tm = TextMessage.objects.get(message_text=text)
    assert tm.original_mc_packet_id == text_packet.id


@pytest.mark.django_db
def test_raw_path_then_channel_text_populates_text_observation(meshcore_feeder, ingest_client):
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    now = timezone.now()
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    path_dump = json.loads((DOCS / "rx_log_data_path.json").read_text())
    rx_time = now.timestamp()

    ingest_client.post(
        url,
        {
            "event_type": "rx_log_data",
            "payload_type": "raw",
            "pkt_hash": path_dump["payload"]["pkt_hash"],
            "rx_time": rx_time,
            "path_hashes": ["f3bcf1"],
            "path_hash_size": 3,
            "raw": path_dump,
        },
        format="json",
    )

    channel_dump = _load(CHANNEL_MSG)
    text = "twin order test message"
    channel_dump = dict(channel_dump)
    channel_dump["payload"] = dict(channel_dump["payload"])
    channel_dump["payload"]["text"] = text

    ingest_client.post(
        url,
        {
            "event_type": "channel_message",
            "payload_type": "channel_text",
            "channel_idx": 0,
            "rx_time": rx_time,
            "text": text,
            "raw": channel_dump,
        },
        format="json",
    )
    text_packet = MeshCoreTextPacket.objects.get(text=text)
    text_obs = MeshCorePacketObservation.objects.get(packet=text_packet)
    assert text_obs.path_hashes == ["f3bcf1"]


@pytest.mark.django_db
def test_raw_path_without_channel_text_twin_leaves_no_text_path(meshcore_feeder, ingest_client):
    now = timezone.now()
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    path_dump = json.loads((DOCS / "rx_log_data_path.json").read_text())
    response = ingest_client.post(
        url,
        {
            "event_type": "rx_log_data",
            "payload_type": "raw",
            "pkt_hash": 999888777,
            "rx_time": now.timestamp(),
            "path_hashes": ["aa"],
            "raw": path_dump,
        },
        format="json",
    )
    assert response.status_code == 201
    assert MeshCoreTextPacket.objects.filter(payload_type=MeshCorePayloadType.CHANNEL_TEXT).count() == 0


@pytest.mark.django_db
def test_raw_path_before_channel_text_outside_30s_within_120s_window(meshcore_feeder, ingest_client):
    """PATH up to 90s before channel_message still twins when default window is 120s."""
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    text_time = timezone.now()
    path_time = text_time - timedelta(seconds=90)
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    path_dump = json.loads((DOCS / "rx_log_data_path.json").read_text())
    channel_dump = _load(CHANNEL_MSG)
    text = "delayed twin window test"
    channel_dump = dict(channel_dump)
    channel_dump["payload"] = dict(channel_dump["payload"])
    channel_dump["payload"]["text"] = text
    channel_dump["payload"]["sender_timestamp"] = 1780416123

    ingest_client.post(
        url,
        {
            "event_type": "rx_log_data",
            "payload_type": "raw",
            "pkt_hash": path_dump["payload"]["pkt_hash"],
            "rx_time": path_time.timestamp(),
            "path_hashes": ["aa", "bb"],
            "path_hash_size": 2,
            "raw": path_dump,
        },
        format="json",
    )

    ingest_client.post(
        url,
        {
            "event_type": "channel_message",
            "payload_type": "channel_text",
            "channel_idx": 0,
            "rx_time": text_time.timestamp(),
            "text": text,
            "raw": channel_dump,
        },
        format="json",
    )

    text_packet = MeshCoreTextPacket.objects.get(text=text)
    text_obs = MeshCorePacketObservation.objects.get(packet=text_packet)
    assert text_obs.path_hashes == ["aa", "bb"]
