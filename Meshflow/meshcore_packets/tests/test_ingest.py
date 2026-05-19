"""MeshCore packet ingest tests."""

from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol
from meshcore_packets.models import MeshCoreRawPacket
from nodes.models import NodeAuth, ObservedNode

FULL_PUBKEY = "b" * 64
PREFIX = "b" * 12


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
    url = reverse("meshcore-packet-ingest")
    response = ingest_client.post(url, payload, format="json")
    assert response.status_code == 201
    assert MeshCoreRawPacket.objects.filter(pkt_hash=12345).exists()
    node = ObservedNode.objects.get(protocol=Protocol.MESHCORE, mc_pubkey=FULL_PUBKEY)
    assert node.long_name == "TestNode"
    assert node.latest_status.latitude == 55.1


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
    url = reverse("meshcore-packet-ingest")
    response = ingest_client.post(url, payload, format="json")
    assert response.status_code == 201
    assert ObservedNode.objects.filter(protocol=Protocol.MESHCORE, mc_pubkey_prefix=PREFIX).exists()


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
    url = reverse("meshcore-packet-ingest")
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
    url = reverse("meshcore-packet-ingest")
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
