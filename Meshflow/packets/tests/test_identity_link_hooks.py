"""Identity link detection at the three key-write sites: on-air NodeInfo, NodeDB upload create and update."""

from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest

from common.meshtastic_identity import identity_fields, normalise_pubkey
from nodes.models import ObservedNode, ObservedNodeIdentityLink
from nodes.services import identity_links
from packets.serializers import NodeSerializer
from packets.services.node_info import NodeInfoPacketService

Link = ObservedNodeIdentityLink
State = Link.State

# PDYt (see nodes/tests/test_identity_links.py).
KEY_B64 = "I9+3Izg6g7w+TIU+EXGyFVYbh9m9sioXeo6RZdlwnS8="
KEY_HEX = normalise_pubkey(KEY_B64)
OLD, NEW = 0x433B82F0, 0x8959691B
MAC = "48:ca:43:3b:82:f0"


def _row(number, key=None):
    fields = identity_fields(key) if key else {}
    return ObservedNode.objects.create(
        meshtastic_node_id=number,
        long_name=f"n{number:x}",
        short_name="N",
        meshtastic_public_key=KEY_HEX if key else None,
        **fields,
    )


def _process(create_node_info_packet, create_managed_node, create_packet_observation, create_user, **packet):
    pkt = create_node_info_packet(**packet)
    observer = create_managed_node()
    observation = create_packet_observation(packet=pkt, observer=observer)
    NodeInfoPacketService().process_packet(pkt, observer, observation, create_user())
    return pkt


@pytest.mark.django_db
def test_nodeinfo_with_key_links_old_to_new(
    create_node_info_packet, create_managed_node, create_packet_observation, create_user
):
    old = _row(OLD, KEY_HEX)
    _row(NEW)
    _process(
        create_node_info_packet,
        create_managed_node,
        create_packet_observation,
        create_user,
        from_int=NEW,
        from_str="!8959691b",
        node_id="!8959691b",
        public_key=KEY_B64,
        mac_address=MAC,
    )
    link = Link.objects.get()
    assert link.old_node == old and link.new_node.meshtastic_node_id == NEW
    assert (link.evidence, link.state) == ("public_key", State.AUTO)


@pytest.mark.django_db
def test_nodeinfo_with_only_the_mac_suggests_the_same_pair(
    create_node_info_packet, create_managed_node, create_packet_observation, create_user
):
    _row(OLD)
    _row(NEW)
    _process(
        create_node_info_packet,
        create_managed_node,
        create_packet_observation,
        create_user,
        from_int=NEW,
        from_str="!8959691b",
        node_id="!8959691b",
        public_key=None,
        mac_address=MAC,
    )
    link = Link.objects.get()
    assert (link.old_node.meshtastic_node_id, link.new_node.meshtastic_node_id) == (OLD, NEW)
    assert (link.evidence, link.confidence, link.state) == ("mac", "medium", State.SUGGESTED)


@pytest.mark.django_db
def test_failing_detection_does_not_fail_nodeinfo_ingest(
    create_node_info_packet, create_managed_node, create_packet_observation, create_user
):
    _row(OLD, KEY_HEX)
    new = _row(NEW)
    with mock.patch.object(identity_links, "_key_holders", side_effect=RuntimeError("boom")):
        _process(
            create_node_info_packet,
            create_managed_node,
            create_packet_observation,
            create_user,
            from_int=NEW,
            from_str="!8959691b",
            node_id="!8959691b",
            public_key=KEY_B64,
            mac_address=MAC,
            long_name="PDYt",
        )
    new.refresh_from_db()
    assert new.long_name == "PDYt" and new.meshtastic_public_key_hex == KEY_HEX
    assert not Link.objects.exists()


def _upsert(instance=None, **data):
    if instance is None:
        data = {"macaddr": "00:00:00:00:00:00", "long_name": "Node", "short_name": "ND", **data}
    serializer = NodeSerializer(instance=instance, data=data, partial=instance is not None)
    assert serializer.is_valid(), serializer.errors
    return serializer.save()


@pytest.mark.django_db
def test_nodedb_upload_creating_a_node_links_it():
    old = _row(OLD, KEY_HEX)
    node = _upsert(id=NEW, macaddr="00:00:00:00:00:00", meshtastic_public_key=KEY_B64)
    link = Link.objects.get()
    assert (link.old_node, link.new_node) == (old, node)


@pytest.mark.django_db
def test_nodedb_upload_updating_a_node_links_it_and_never_uses_its_mac():
    _row(OLD)
    node = _row(NEW)
    _upsert(node, id=NEW, macaddr=MAC)  # NodeDB MAC alone: never MAC evidence
    assert not Link.objects.exists()
    old = ObservedNode.objects.get(meshtastic_node_id=OLD)
    for field, value in identity_fields(KEY_HEX).items():
        setattr(old, field, value)
    old.save()
    _upsert(node, id=NEW, meshtastic_public_key=KEY_B64)
    link = Link.objects.get()
    assert (link.old_node, link.new_node) == (old, node)


@pytest.mark.django_db
def test_failing_detection_does_not_fail_a_nodedb_upload():
    _row(OLD, KEY_HEX)
    with mock.patch.object(identity_links, "_key_holders", side_effect=RuntimeError("boom")):
        node = _upsert(id=NEW, meshtastic_public_key=KEY_B64)
    assert node.meshtastic_public_key_hex == KEY_HEX
    assert not Link.objects.exists()


@pytest.mark.django_db
def test_nodedb_upload_costs_one_identity_query_per_node_on_the_no_work_path():
    count = 20
    keys = [f"{i:02x}" * 32 for i in range(1, count + 1)]
    with CaptureQueriesContext(connection) as queries:
        for i, key in enumerate(keys):
            _upsert(id=0x70000000 + i, meshtastic_public_key=key)
    holder_queries = [q for q in queries.captured_queries if '"meshtastic_public_key_hex" = ' in q["sql"]]
    assert len(holder_queries) == count
    assert not Link.objects.exists()


def _identity_queries(queries):
    """The reads detection makes: link rows, holders of a key, MAC candidates (the node's own UPDATE is not one)."""
    markers = ("nodes_observednodeidentitylink", '"meshtastic_public_key_hex" = ', '"mac_addr" = ')
    return [
        q for q in queries.captured_queries if q["sql"].startswith("SELECT") and any(m in q["sql"] for m in markers)
    ]


@pytest.mark.django_db
def test_repeated_identical_nodeinfo_costs_no_identity_queries(
    create_node_info_packet, create_managed_node, create_packet_observation, create_user
):
    _row(NEW)
    packet = dict(
        from_int=NEW,
        from_str="!8959691b",
        node_id="!8959691b",
        public_key=KEY_B64,
        mac_address=MAC,
        long_name="PDYt",
    )
    args = (create_node_info_packet, create_managed_node, create_packet_observation, create_user)
    with CaptureQueriesContext(connection) as first:
        _process(*args, **packet)  # the first one is a real change: detection reads
    assert _identity_queries(first)
    with CaptureQueriesContext(connection) as queries:
        for _ in range(3):
            _process(*args, **packet)
    assert _identity_queries(queries) == []


@pytest.mark.django_db
def test_nodeinfo_with_a_changed_mac_or_key_runs_detection_again(
    create_node_info_packet, create_managed_node, create_packet_observation, create_user
):
    _row(OLD)
    _row(NEW)
    args = (create_node_info_packet, create_managed_node, create_packet_observation, create_user)
    base = dict(from_int=NEW, from_str="!8959691b", node_id="!8959691b", public_key=None)
    _process(*args, **base, mac_address="02:00:00:00:00:01")
    assert not Link.objects.exists()
    _process(*args, **base, mac_address=MAC)  # a different MAC: a real change
    assert Link.objects.get().state == State.SUGGESTED


@pytest.mark.django_db
def test_repeated_identical_nodedb_upload_costs_no_identity_queries():
    with CaptureQueriesContext(connection) as first:
        node = _upsert(id=NEW, meshtastic_public_key=KEY_B64)
    assert _identity_queries(first)
    with CaptureQueriesContext(connection) as queries:
        for _ in range(3):
            _upsert(node, id=NEW, meshtastic_public_key=KEY_B64)
    assert _identity_queries(queries) == []
