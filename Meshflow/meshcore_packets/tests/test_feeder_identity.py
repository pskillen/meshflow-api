"""HTTP tests for MeshCore feeder disambiguation (#295)."""

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol
from meshcore_packets.tests.conftest import (
    FEEDER_B_MC_PUBKEY,
    FEEDER_B_MC_PUBKEY_PREFIX,
    FEEDER_MC_PUBKEY,
    FEEDER_MC_PUBKEY_PREFIX,
    feeder_url,
)
from nodes.models import NodeAuth


@pytest.fixture
def shared_key_two_feeders(create_managed_node, create_node_api_key):
    constellation = create_managed_node(protocol=Protocol.MESHCORE).constellation
    node_a = create_managed_node(
        meshtastic_node_id=0,
        protocol=Protocol.MESHCORE,
        constellation=constellation,
        name="Feeder A",
        mc_pubkey=FEEDER_MC_PUBKEY,
    )
    node_b = create_managed_node(
        meshtastic_node_id=0,
        protocol=Protocol.MESHCORE,
        constellation=constellation,
        name="Feeder B",
        mc_pubkey=FEEDER_B_MC_PUBKEY,
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node_a)
    NodeAuth.objects.create(api_key=api_key, node=node_b)
    return {
        "api_key": api_key,
        "node_a": node_a,
        "node_b": node_b,
    }


@pytest.mark.django_db
def test_bot_version_scoped_to_feeder_a(shared_key_two_feeders):
    api_key = shared_key_two_feeders["api_key"]
    node_a = shared_key_two_feeders["node_a"]
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=api_key.key)
    url = feeder_url("meshcore-feeder-bot-version", FEEDER_MC_PUBKEY_PREFIX)
    response = client.put(
        url,
        {"bot_version": "meshflow-bot-test-a"},
        format="json",
        HTTP_X_MESHCORE_FEEDER_PUBKEY=FEEDER_MC_PUBKEY,
    )
    assert response.status_code == 200
    node_a.refresh_from_db()
    assert node_a.bot_version == "meshflow-bot-test-a"
    shared_key_two_feeders["node_b"].refresh_from_db()
    assert shared_key_two_feeders["node_b"].bot_version is None


@pytest.mark.django_db
def test_bot_version_wrong_prefix_403(shared_key_two_feeders):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=shared_key_two_feeders["api_key"].key)
    url = feeder_url("meshcore-feeder-bot-version", "deadbeef0000")
    response = client.put(url, {"bot_version": "x"}, format="json")
    assert response.status_code == 403
    assert response.data["code"] == "feeder_not_linked"


@pytest.mark.django_db
def test_ingest_attributes_observer_per_prefix(shared_key_two_feeders):
    from django.utils import timezone

    api_key = shared_key_two_feeders["api_key"]
    now = timezone.now()
    payload = {
        "event_type": "advertisement",
        "payload_type": "advert",
        "from_pubkey": "d" * 64,
        "pkt_hash": 999001,
        "rx_time": now.timestamp(),
        "adv_name": "Remote",
    }
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=api_key.key)
    url_b = feeder_url("meshcore-feeder-packet-ingest", FEEDER_B_MC_PUBKEY_PREFIX)
    response = client.post(url_b, payload, format="json")
    assert response.status_code == 201
    from meshcore_packets.models import MeshCoreRawPacket

    packet = MeshCoreRawPacket.objects.get(pkt_hash=999001)
    assert packet.observer_id == shared_key_two_feeders["node_b"].internal_id
