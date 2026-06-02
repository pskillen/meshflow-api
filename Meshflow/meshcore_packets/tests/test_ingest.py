"""MeshCore packet ingest tests."""

from datetime import timedelta

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol
from meshcore_packets.models import MeshCorePayloadType, MeshCoreRawPacket
from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.tests.conftest import FEEDER_MC_PUBKEY_PREFIX, feeder_url
from nodes.models import MeshCoreLocationSource, NodeAuth, ObservedNode, Position
from text_messages.models import TextMessage

FULL_PUBKEY = "b" * 64
PREFIX = "b" * 12
WMF_PUBKEY = "f3bcf18b78deee33596d29d49aa6891d30ac6e2c97e7e6a9b81907f1470afcfc"
WMF_RX_LOG_ENVELOPE = {
    "protocol": "meshcore",
    "event_type": "rx_log_data",
    "payload": {
        "recv_time": 1778101899,
        "snr": -1.5,
        "rssi": -111,
        "payload_typename": "ADVERT",
        "pkt_hash": 3654312717,
        "adv_name": "WMF",
        "adv_key": WMF_PUBKEY,
        "adv_timestamp": 1778101841,
        "adv_lat": 55.99578,
        "adv_lon": -4.09121,
        "adv_type": 2,
    },
    "attributes": {"recv_time": 1778101899},
}


@pytest.fixture
def ingest_client(meshcore_feeder):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=meshcore_feeder["api_key"].key)
    return client


@pytest.mark.django_db
def test_meshcore_advert_ingest_creates_packet_and_node(ingest_client, meshcore_feeder):
    now = timezone.now()
    payload = {
        "event_type": "advertisement",
        "payload_type": "advert",
        "from_pubkey": FULL_PUBKEY,
        "pkt_hash": 12345,
        "rx_time": now.timestamp(),
        "rx_rssi": -70.0,
        "adv_name": "TestNode",
        "adv_lat": 55.1,
        "adv_lon": -4.2,
        "raw": {"public_key": FULL_PUBKEY},
    }
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    response = ingest_client.post(url, payload, format="json")
    assert response.status_code == 201
    assert MeshCoreRawPacket.objects.filter(pkt_hash=12345).exists()
    node = ObservedNode.objects.get(protocol=Protocol.MESHCORE, mc_pubkey=FULL_PUBKEY)
    assert node.long_name == "TestNode"
    assert node.latest_status.latitude == 55.1
    assert Position.objects.filter(node=node).count() == 1
    position = Position.objects.get(node=node)
    assert position.meshcore_location_source == MeshCoreLocationSource.ADVERT
    assert position.original_mc_packet_id is not None


@pytest.mark.django_db
def test_meshcore_rx_log_data_advert_ingest(ingest_client, meshcore_feeder):
    now = timezone.now()
    payload = {
        "event_type": "rx_log_data",
        "payload_type": "advert",
        "from_pubkey": WMF_PUBKEY,
        "pkt_hash": 3654312717,
        "rx_time": now.timestamp(),
        "rx_rssi": -111.0,
        "adv_name": "WMF",
        "adv_lat": 55.99578,
        "adv_lon": -4.09121,
        "raw": {
            "meshcore": True,
            "type": "rx_log_data",
            "payload": WMF_RX_LOG_ENVELOPE["payload"],
            "attributes": WMF_RX_LOG_ENVELOPE["attributes"],
        },
    }
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    response = ingest_client.post(url, payload, format="json")
    assert response.status_code == 201
    packet = MeshCoreRawPacket.objects.get(pkt_hash=3654312717)
    assert packet.event_type == "rx_log_data"
    node = ObservedNode.objects.get(protocol=Protocol.MESHCORE, mc_pubkey=WMF_PUBKEY)
    assert node.long_name == "WMF"
    assert node.meshcore_adv_type == 2
    assert node.latest_status.latitude == pytest.approx(55.99578)
    assert node.latest_status.longitude == pytest.approx(-4.09121)
    assert Position.objects.filter(node=node).count() == 1


@pytest.mark.django_db
def test_meshcore_rx_log_data_advert_nested_coords_only(ingest_client, meshcore_feeder):
    """Position from adv_lat/adv_lon nested under raw.payload when top-level coords omitted."""
    now = timezone.now()
    pkt_hash = 3654312718
    payload = {
        "event_type": "rx_log_data",
        "payload_type": "advert",
        "pkt_hash": pkt_hash,
        "rx_time": now.timestamp(),
        "raw": {
            "meshcore": True,
            "type": "rx_log_data",
            "payload": {
                "payload_typename": "ADVERT",
                "adv_key": WMF_PUBKEY,
                "adv_name": "WMF",
                "adv_lat": 55.99578,
                "adv_lon": -4.09121,
                "adv_timestamp": 1778101841,
            },
            "attributes": {},
        },
    }
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    response = ingest_client.post(url, payload, format="json")
    assert response.status_code == 201
    node = ObservedNode.objects.get(protocol=Protocol.MESHCORE, mc_pubkey=WMF_PUBKEY)
    assert node.latest_status.latitude == pytest.approx(55.99578)
    assert Position.objects.filter(node=node).count() == 1


@pytest.mark.django_db
def test_meshcore_advertisement_without_coords_no_position(ingest_client, meshcore_feeder):
    """advertisement events without adv_lat/adv_lon create identity only."""
    now = timezone.now()
    pubkey = "d" * 64
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    ingest_client.post(
        url,
        {
            "event_type": "advertisement",
            "payload_type": "advert",
            "from_pubkey": pubkey,
            "pkt_hash": 88001,
            "rx_time": now.timestamp(),
            "adv_lat": 55.0,
            "adv_lon": -4.0,
            "raw": {},
        },
        format="json",
    )
    node = ObservedNode.objects.get(protocol=Protocol.MESHCORE, mc_pubkey=pubkey)
    assert node.latest_status.latitude == 55.0

    ingest_client.post(
        url,
        {
            "event_type": "advertisement",
            "payload_type": "advert",
            "from_pubkey": pubkey,
            "pkt_hash": 88002,
            "rx_time": (now + timedelta(seconds=60)).timestamp(),
            "adv_name": "Renamed",
            "raw": {"public_key": pubkey},
        },
        format="json",
    )
    node.refresh_from_db()
    assert node.long_name == "Renamed"
    assert node.latest_status.latitude == 55.0
    assert node.latest_status.longitude == -4.0
    assert Position.objects.filter(node=node).count() == 1


@pytest.mark.django_db
def test_meshcore_channel_text_creates_text_message(ingest_client, meshcore_feeder):
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    now = timezone.now()
    payload = {
        "event_type": "channel_message",
        "payload_type": "channel_text",
        "channel_idx": 0,
        "pkt_hash": 4242,
        "rx_time": now.timestamp(),
        "text": "mesh hello",
        "raw": {},
    }
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    response = ingest_client.post(url, payload, format="json")
    assert response.status_code == 201
    assert TextMessage.objects.filter(message_text="mesh hello").exists()
    tm = TextMessage.objects.get(message_text="mesh hello")
    assert tm.sender_id is None
    assert tm.channel_id is not None


@pytest.mark.django_db
def test_meshcore_contact_text_ingest(ingest_client):
    now = timezone.now()
    payload = {
        "event_type": "contact_message",
        "payload_type": "contact_text",
        "from_pubkey_prefix": PREFIX,
        "pkt_hash": 999,
        "rx_time": now.timestamp(),
        "text": "hello dm",
        "channel_idx": 0,
        "raw": {},
    }
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    response = ingest_client.post(url, payload, format="json")
    assert response.status_code == 201
    assert ObservedNode.objects.filter(protocol=Protocol.MESHCORE, mc_pubkey_prefix=PREFIX).exists()


@pytest.mark.django_db
def test_meshcore_channel_text_without_pkt_hash_dedup_same_feeder(ingest_client, meshcore_feeder):
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    now = timezone.now()
    payload = {
        "event_type": "channel_message",
        "payload_type": "channel_text",
        "channel_idx": 0,
        "rx_time": now.timestamp(),
        "text": "dedup ping",
        "raw": {
            "protocol": "meshcore",
            "event_type": "channel_message",
            "payload": {"sender_timestamp": 1234567890, "text": "dedup ping"},
        },
    }
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    r1 = ingest_client.post(url, payload, format="json")
    r2 = ingest_client.post(url, payload, format="json")
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.data["packet_id"] == r2.data["packet_id"]
    assert MeshCoreRawPacket.objects.filter(payload_type=MeshCorePayloadType.CHANNEL_TEXT).count() == 1
    packet = MeshCoreRawPacket.objects.get(id=r1.data["packet_id"])
    assert packet.pkt_hash is not None
    assert TextMessage.objects.filter(message_text="dedup ping").count() == 1


@pytest.mark.django_db
def test_meshcore_dedup_returns_existing(ingest_client):
    now = timezone.now()
    payload = {
        "event_type": "advertisement",
        "payload_type": "advert",
        "from_pubkey": FULL_PUBKEY,
        "pkt_hash": 555,
        "rx_time": now.timestamp(),
        "raw": {},
    }
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    r1 = ingest_client.post(url, payload, format="json")
    r2 = ingest_client.post(url, payload, format="json")
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert MeshCoreRawPacket.objects.filter(pkt_hash=555).count() == 1


@pytest.mark.django_db
def test_meshcore_ingest_requires_mc_feeder(create_managed_node, create_node_api_key):
    mt_node = create_managed_node(protocol=Protocol.MESHTASTIC)
    api_key = create_node_api_key()
    NodeAuth.objects.create(api_key=api_key, node=mt_node)
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=api_key.key)
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    response = client.post(
        url,
        {
            "event_type": "advertisement",
            "payload_type": "advert",
            "from_pubkey": FULL_PUBKEY,
            "rx_time": timezone.now().timestamp(),
            "raw": {},
        },
        format="json",
    )
    assert response.status_code == 403
