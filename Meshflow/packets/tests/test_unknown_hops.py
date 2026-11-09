"""Bitfield storage and the unknown-hops rule (#450): hop_start 0 without a bitfield is not direct."""

from django.urls import reverse

import pytest
from rest_framework.test import APIClient

from dx_monitoring.services import is_direct_packet_observation
from packets.models import PacketObservation
from packets.serializers import PrefetchedPacketObservationSerializer

NODE = 0x1A2B3C4D


@pytest.fixture
def feeder(create_node_auth):
    auth = create_node_auth()
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=auth.api_key.key)
    return {"client": client, "node": auth.node}


def _ingest(feeder, decoded, packet_id=7001, **extra):
    body = {"id": packet_id, "from": NODE, "to": 0xFFFFFFFF, "decoded": decoded, "rxTime": 1672531200}
    body.update(extra)
    url = reverse("meshtastic-packet-ingest", kwargs={"node_id": feeder["node"].meshtastic_node_id})
    return feeder["client"].post(url, body, format="json")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "decoded,expected",
    [
        ({"portnum": "TEXT_MESSAGE_APP", "text": "hi", "bitfield": 1}, 1),
        ({"portnum": "TEXT_MESSAGE_APP", "text": "hi", "bitfield": 0}, 0),
        ({"portnum": "TEXT_MESSAGE_APP", "text": "hi", "bitfield": 4294967295}, 4294967295),
        ({"portnum": "TEXT_MESSAGE_APP", "text": "hi", "bitfield": 40000}, 40000),
        ({"portnum": "TEXT_MESSAGE_APP", "text": "hi"}, None),
        ({"portnum": "STORE_FORWARD_APP", "bitfield": 3}, 3),
        ({"portnum": "STORE_FORWARD_APP", "bitfield": 0}, 0),
        ({"portnum": "STORE_FORWARD_APP"}, None),
    ],
)
def test_bitfield_is_stored_on_the_observation(feeder, decoded, expected):
    resp = _ingest(feeder, decoded, hopStart=3, hopLimit=3)
    assert resp.status_code == 201, resp.content
    assert PacketObservation.objects.get().bitfield == expected


def _observation(create_packet_observation, hop_start, hop_limit, bitfield=None):
    return create_packet_observation(hop_start=hop_start, hop_limit=hop_limit, bitfield=bitfield)


def _serialised(observation):
    data = PrefetchedPacketObservationSerializer(observation, context={}).data
    return data["hop_count"], data["direct_from_sender"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "hop_start,hop_limit,bitfield,hop_count,direct",
    [
        (0, 0, None, None, False),  # unknown
        (0, 0, 0, 0, True),
        (3, 3, None, 0, True),
        (3, 1, None, 2, False),
        (3, 0, None, 3, False),  # hops exhausted
        (None, None, None, None, False),
    ],
)
def test_serializer_and_dx_agree(create_packet_observation, hop_start, hop_limit, bitfield, hop_count, direct):
    observation = _observation(create_packet_observation, hop_start, hop_limit, bitfield)
    assert _serialised(observation) == (hop_count, direct)
    assert is_direct_packet_observation(observation) is direct


@pytest.mark.django_db
def test_direct_observation_reads_stored_bitfield(create_packet_observation):
    observation = _observation(create_packet_observation, 0, 0, bitfield=0)
    observation.refresh_from_db()
    assert observation.bitfield == 0
    assert is_direct_packet_observation(observation) is True
