"""path_hashes stored per observation only (#369)."""

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from meshcore_packets.models import MeshCorePacketObservation, MeshCoreRawPacket
from meshcore_packets.tests.conftest import (
    FEEDER_B_MC_PUBKEY,
    FEEDER_B_MC_PUBKEY_PREFIX,
    FEEDER_MC_PUBKEY_PREFIX,
    feeder_url,
)
from nodes.models import NodeAuth

FULL_PUBKEY = "b" * 64


@pytest.fixture
def ingest_client(meshcore_feeder):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=meshcore_feeder["api_key"].key)
    return client


@pytest.fixture
def second_mc_feeder(create_managed_node, create_node_api_key):
    from common.protocol import Protocol

    node = create_managed_node(
        meshtastic_node_id=None,
        protocol=Protocol.MESHCORE,
        name="MC Feeder B",
        mc_pubkey=FEEDER_B_MC_PUBKEY,
    )
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    return {"node": node, "api_key": api_key}


@pytest.mark.django_db
def test_path_hashes_on_observation_only_two_feeders(ingest_client, meshcore_feeder, second_mc_feeder):
    now = timezone.now()
    base = {
        "event_type": "advertisement",
        "payload_type": "advert",
        "from_pubkey": FULL_PUBKEY,
        "pkt_hash": 77701,
        "rx_time": now.timestamp(),
        "raw": {},
    }
    url_a = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    url_b = feeder_url("meshcore-feeder-packet-ingest", FEEDER_B_MC_PUBKEY_PREFIX)

    client_b = APIClient()
    client_b.credentials(HTTP_X_API_KEY=second_mc_feeder["api_key"].key)

    r1 = ingest_client.post(url_a, {**base, "path_hashes": ["aa", "bb"]}, format="json")
    r2 = client_b.post(url_b, {**base, "path_hashes": ["cc", "dd"]}, format="json")
    assert r1.status_code == 201
    assert r2.status_code == 201

    assert MeshCoreRawPacket.objects.filter(pkt_hash=77701).count() == 1
    packet = MeshCoreRawPacket.objects.get(pkt_hash=77701)
    field_names = {f.name for f in MeshCoreRawPacket._meta.get_fields()}
    assert "path_hashes" not in field_names

    observations = MeshCorePacketObservation.objects.filter(packet=packet).order_by("observer__name")
    assert observations.count() == 2
    paths = {tuple(obs.path_hashes or []) for obs in observations}
    assert paths == {("aa", "bb"), ("cc", "dd")}


@pytest.mark.django_db
def test_observation_path_hashes_updated_on_reingest(ingest_client, meshcore_feeder):
    now = timezone.now()
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    payload = {
        "event_type": "advertisement",
        "payload_type": "advert",
        "from_pubkey": FULL_PUBKEY,
        "pkt_hash": 77702,
        "rx_time": now.timestamp(),
        "path_hashes": ["11"],
        "raw": {},
    }
    ingest_client.post(url, payload, format="json")
    ingest_client.post(url, {**payload, "path_hashes": ["22", "33"]}, format="json")

    packet = MeshCoreRawPacket.objects.get(pkt_hash=77702)
    obs = MeshCorePacketObservation.objects.get(packet=packet, observer=meshcore_feeder["node"])
    assert obs.path_hashes == ["22", "33"]
