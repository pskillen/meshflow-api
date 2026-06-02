"""Cross-feeder channel_text dedup (#387)."""

import json
from pathlib import Path

from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol
from meshcore_packets.models import (
    MeshCorePacketObservation,
    MeshCorePayloadType,
    MeshCoreRawPacket,
)
from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.tests.conftest import (
    FEEDER_B_MC_PUBKEY_PREFIX,
    FEEDER_MC_PUBKEY_PREFIX,
    feeder_url,
)
from nodes.models import NodeAuth
from text_messages.models import TextMessage

SENDER_TIMESTAMP = 1780409317
MESSAGE_TEXT = "PDY4 Paddy Mobile 4: Ping"


def _channel_text_payload(*, channel_idx: int, rx_time, rx_rssi: float):
    return {
        "event_type": "channel_message",
        "payload_type": "channel_text",
        "channel_idx": channel_idx,
        "rx_time": rx_time.timestamp(),
        "rx_rssi": rx_rssi,
        "text": MESSAGE_TEXT,
        "raw": {
            "protocol": "meshcore",
            "event_type": "channel_message",
            "payload": {
                "type": "CHAN",
                "channel_idx": channel_idx,
                "sender_timestamp": SENDER_TIMESTAMP,
                "text": MESSAGE_TEXT,
            },
        },
    }


@pytest.fixture
def second_mc_feeder(meshcore_feeder, create_managed_node, create_node_api_key):
    from meshcore_packets.tests.conftest import FEEDER_B_MC_PUBKEY

    constellation = meshcore_feeder["node"].constellation
    node = create_managed_node(
        meshtastic_node_id=None,
        protocol=Protocol.MESHCORE,
        name="MC Feeder B",
        mc_pubkey=FEEDER_B_MC_PUBKEY,
        constellation=constellation,
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    return {"node": node, "api_key": api_key}


def _setup_hashtag_channels(meshcore_feeder, second_mc_feeder):
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 1, "name": "test", "mc_channel_type": "HASHTAG", "mc_hashtag": "test"}],
    )
    reconcile_mc_channels(
        second_mc_feeder["node"],
        [{"mc_channel_idx": 2, "name": "test", "mc_channel_type": "HASHTAG", "mc_hashtag": "test"}],
    )


@pytest.mark.django_db
@pytest.mark.parametrize("first_feeder", ("a", "b"))
def test_cross_feeder_channel_text_one_packet_two_observations(
    meshcore_feeder,
    second_mc_feeder,
    first_feeder,
):
    """Same on-air channel post from two feeders → one packet, one TextMessage, heard×2."""
    _setup_hashtag_channels(meshcore_feeder, second_mc_feeder)
    now = timezone.now()
    feeders = {
        "a": (meshcore_feeder, 1, FEEDER_MC_PUBKEY_PREFIX),
        "b": (second_mc_feeder, 2, FEEDER_B_MC_PUBKEY_PREFIX),
    }
    first, second = (feeders["a"], feeders["b"]) if first_feeder == "a" else (feeders["b"], feeders["a"])

    def post(feeder_info, rssi):
        feeder, channel_idx, prefix = feeder_info
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=feeder["api_key"].key)
        url = feeder_url("meshcore-feeder-packet-ingest", prefix)
        return client.post(
            url,
            _channel_text_payload(channel_idx=channel_idx, rx_time=now, rx_rssi=rssi),
            format="json",
        )

    r1 = post(first, -40.0)
    r2 = post(second, -90.0)
    assert r1.status_code == 201
    assert r2.status_code == 201
    packet_id_a = r1.data["packet_id"]
    packet_id_b = r2.data["packet_id"]
    assert packet_id_a == packet_id_b

    assert MeshCoreRawPacket.objects.filter(payload_type=MeshCorePayloadType.CHANNEL_TEXT).count() == 1
    packet = MeshCoreRawPacket.objects.get(id=packet_id_a)
    assert packet.pkt_hash is not None
    assert MeshCorePacketObservation.objects.filter(packet=packet).count() == 2
    assert TextMessage.objects.filter(message_text=MESSAGE_TEXT).count() == 1

    tm = TextMessage.objects.get(message_text=MESSAGE_TEXT)
    list_url = reverse("textmessage-list")
    response = APIClient().get(list_url, {"channel_id": tm.channel_id})
    assert response.status_code == 200
    row = next(item for item in response.data["results"] if item["id"] == str(tm.id))
    assert len(row["heard"]) == 2


DOCS = Path(__file__).resolve().parents[3] / "docs" / "packets" / "meshcore"
PATH_DUMP = json.loads((DOCS / "rx_log_data_path.json").read_text())


@pytest.mark.django_db
def test_cross_feeder_path_twin_on_second_feeder_observation(meshcore_feeder, second_mc_feeder):
    """PATH on feeder B attaches to deduped packet via B's observation, not packet.observer only."""
    _setup_hashtag_channels(meshcore_feeder, second_mc_feeder)
    now = timezone.now()
    text = "cross feeder path twin test"
    ts = 1780416000

    def channel_payload(channel_idx, feeder_prefix, feeder_info):
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=feeder_info["api_key"].key)
        return client.post(
            feeder_url("meshcore-feeder-packet-ingest", feeder_prefix),
            {
                "event_type": "channel_message",
                "payload_type": "channel_text",
                "channel_idx": channel_idx,
                "rx_time": now.timestamp(),
                "text": text,
                "raw": {
                    "protocol": "meshcore",
                    "event_type": "channel_message",
                    "payload": {
                        "channel_idx": channel_idx,
                        "sender_timestamp": ts,
                        "text": text,
                    },
                },
            },
            format="json",
        )

    r_a = channel_payload(1, FEEDER_MC_PUBKEY_PREFIX, meshcore_feeder)
    r_b = channel_payload(2, FEEDER_B_MC_PUBKEY_PREFIX, second_mc_feeder)
    assert r_a.status_code == 201
    assert r_b.status_code == 201
    packet_id = r_a.data["packet_id"]
    assert packet_id == r_b.data["packet_id"]

    client_b = APIClient()
    client_b.credentials(HTTP_X_API_KEY=second_mc_feeder["api_key"].key)
    r_path = client_b.post(
        feeder_url("meshcore-feeder-packet-ingest", FEEDER_B_MC_PUBKEY_PREFIX),
        {
            "event_type": "rx_log_data",
            "payload_type": "raw",
            "pkt_hash": PATH_DUMP["payload"]["pkt_hash"],
            "rx_time": now.timestamp(),
            "path_hashes": ["6edc9b", "4cd741", "f3bcf1"],
            "path_hash_size": 3,
            "raw": PATH_DUMP,
        },
        format="json",
    )
    assert r_path.status_code == 201

    packet = MeshCoreRawPacket.objects.get(id=packet_id)
    obs_b = MeshCorePacketObservation.objects.get(packet=packet, observer=second_mc_feeder["node"])
    assert obs_b.path_hashes == ["6edc9b", "4cd741", "f3bcf1"]
