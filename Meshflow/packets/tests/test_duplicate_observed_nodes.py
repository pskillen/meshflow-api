"""Duplicate Meshtastic ObservedNode rows must not break ingest (#480 part 1), and creates are atomic (part 2).

The unique index normally forbids duplicates; the legacy-state tests drop it to rebuild what a pre-constraint
database (or a restore) could hold, and the test transaction rolls the drop back.
"""

from datetime import timedelta
from unittest import mock

from django.db import IntegrityError, connection
from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol
from nodes.models import NodeLatestStatus, ObservedNode, Position
from nodes.services.observed_nodes import get_meshtastic_observed_node, get_or_create_meshtastic_observed_node
from packets.models import MessagePacket, PositionPacket

NODE = 0x1A2B3C4D
NODE_STR = "!1a2b3c4d"
RX = 1672531200


@pytest.fixture
def feeder(create_node_auth):
    auth = create_node_auth()
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=auth.api_key.key)
    return {"client": client, "node": auth.node}


@pytest.fixture
def allow_duplicates(db):
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX nodes_observednode_mt_node_id_unique")


@pytest.fixture
def duplicates(allow_duplicates):
    """Two Meshtastic rows for NODE: the older one is the keeper."""
    now = timezone.now()
    keeper = ObservedNode.objects.create(
        protocol=Protocol.MESHTASTIC, meshtastic_node_id=NODE, long_name="Keeper", short_name="KEEP"
    )
    other = ObservedNode.objects.create(
        protocol=Protocol.MESHTASTIC, meshtastic_node_id=NODE, long_name="Other", short_name="OTHR"
    )
    ObservedNode.objects.filter(pk=keeper.pk).update(created_at=now - timedelta(days=2))
    ObservedNode.objects.filter(pk=other.pk).update(created_at=now - timedelta(days=1))
    keeper.refresh_from_db()
    other.refresh_from_db()
    return keeper, other


def _ingest(feeder, payload):
    url = reverse("meshtastic-packet-ingest", kwargs={"node_id": feeder["node"].meshtastic_node_id})
    return feeder["client"].post(url, payload, format="json")


def _position_payload(packet_id=1001):
    return {
        "id": packet_id,
        "from": NODE,
        "to": 0xFFFFFFFF,
        "decoded": {"portnum": "POSITION_APP", "position": {"latitude": 51.5, "longitude": -0.1, "altitude": 10}},
        "rxTime": RX,
        "hopStart": 3,
        "hopLimit": 3,
    }


def _text_payload(packet_id=1002):
    return {
        "id": packet_id,
        "from": NODE,
        "to": 0xFFFFFFFF,
        "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "hello"},
        "rxTime": RX,
        "hopStart": 3,
        "hopLimit": 3,
    }


@pytest.mark.django_db
def test_helper_returns_oldest_row_when_legacy_duplicates_exist(duplicates):
    keeper, _ = duplicates
    assert get_meshtastic_observed_node(NODE).pk == keeper.pk


@pytest.mark.django_db
def test_helper_orders_null_created_at_last(allow_duplicates):
    older = ObservedNode.objects.create(
        protocol=Protocol.MESHTASTIC, meshtastic_node_id=NODE, long_name="A", short_name="A"
    )
    nulled = ObservedNode.objects.create(
        protocol=Protocol.MESHTASTIC, meshtastic_node_id=NODE, long_name="B", short_name="B"
    )
    ObservedNode.objects.filter(pk=nulled.pk).update(created_at=None)
    assert get_meshtastic_observed_node(NODE).pk == older.pk


@pytest.mark.django_db
def test_helper_ignores_meshcore_rows_and_missing():
    ObservedNode.objects.create(
        protocol=Protocol.MESHCORE, mc_pubkey="ab" * 32, long_name="MC", short_name="MC", meshtastic_node_id=NODE
    )
    assert get_meshtastic_observed_node(NODE) is None


@pytest.mark.django_db
def test_get_or_create_creates_then_reuses():
    node, created = get_or_create_meshtastic_observed_node(NODE, defaults={"long_name": "New", "short_name": "NEW"})
    assert created
    assert node.protocol == Protocol.MESHTASTIC
    again, created = get_or_create_meshtastic_observed_node(NODE, defaults={"long_name": "x", "short_name": "x"})
    assert not created
    assert again.pk == node.pk


@pytest.mark.django_db
def test_position_ingest_with_duplicates_attaches_to_keeper(feeder, duplicates):
    keeper, other = duplicates
    response = _ingest(feeder, _position_payload())
    assert response.status_code == 201, response.content
    assert PositionPacket.objects.filter(from_int=NODE).count() == 1
    assert Position.objects.filter(node=keeper).count() == 1
    assert Position.objects.filter(node=other).count() == 0


@pytest.mark.django_db
def test_text_message_ingest_with_duplicates_uses_receiver_path(feeder, duplicates):
    keeper, other = duplicates
    response = _ingest(feeder, _text_payload())
    assert response.status_code == 201, response.content
    assert MessagePacket.objects.filter(from_int=NODE).count() == 1
    # The inferred-max-hops receiver wrote its status on the keeper, not the newer row.
    assert NodeLatestStatus.objects.filter(node=keeper, meshtastic_inferred_max_hops=3).exists()
    assert not NodeLatestStatus.objects.filter(node=other).exists()
    assert ObservedNode.objects.filter(meshtastic_node_id=NODE).count() == 2


@pytest.mark.django_db
def test_node_upsert_with_duplicates_updates_keeper(feeder, duplicates):
    keeper, other = duplicates
    url = reverse("meshtastic-node-upsert", kwargs={"node_id": feeder["node"].meshtastic_node_id})
    response = feeder["client"].post(
        url,
        {
            "id": NODE,
            "macaddr": "aa:bb:cc:dd:ee:ff",
            "user": {"long_name": "Renamed", "short_name": "RNMD"},
        },
        format="json",
    )
    assert response.status_code in (200, 201), response.content
    keeper.refresh_from_db()
    other.refresh_from_db()
    assert keeper.mac_addr == "aa:bb:cc:dd:ee:ff"
    assert other.mac_addr is None
    assert ObservedNode.objects.filter(meshtastic_node_id=NODE).count() == 2


@pytest.mark.django_db
def test_ingest_400_names_the_node(feeder, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("packets.serializers.PacketIngestSerializer.save", boom)
    response = _ingest(feeder, _text_payload())
    assert response.status_code == 400
    assert response.json()["node"] == NODE_STR
    assert response.json()["message"] == "kaboom"


@pytest.mark.django_db
def test_get_or_create_loses_a_create_race_and_returns_the_winner():
    """Both callers miss the lookup; the second create hits the unique index and falls back to the winner's row."""
    winner = ObservedNode.objects.create(
        protocol=Protocol.MESHTASTIC, meshtastic_node_id=NODE, long_name="Winner", short_name="WIN"
    )
    lookups = iter([None, winner])  # the first lookup misses; the re-read after the IntegrityError finds the winner

    with mock.patch(
        "nodes.services.observed_nodes.get_meshtastic_observed_node", side_effect=lambda _id: next(lookups)
    ):
        node, created = get_or_create_meshtastic_observed_node(NODE, defaults={"long_name": "Loser", "short_name": "L"})

    assert not created
    assert node.pk == winner.pk
    assert ObservedNode.objects.filter(meshtastic_node_id=NODE).count() == 1


@pytest.mark.django_db
def test_get_or_create_reraises_an_integrity_error_that_is_not_the_race():
    with mock.patch.object(type(ObservedNode.objects), "get_or_create", side_effect=IntegrityError("other")):
        with pytest.raises(IntegrityError):
            get_or_create_meshtastic_observed_node(NODE)
