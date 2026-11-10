"""Goldens for the Meshtastic 2.7/2.8 capture subset (``docs/packets/meshtastic-2.8``), and a few sequences.

Every wire body is what the bot sends for one captured packet; the golden is what the API stores and does with it.
Regenerate with ``MESHFLOW_REGEN_GOLDENS=1`` (and check the diff by hand).
"""

from django.utils import timezone

import pytest

from nodes.models import NodeLatestStatus, ObservedNode
from packets.models import MtRawPacket, PacketObservation
from packets.tests import goldens

pytestmark = pytest.mark.django_db


def _run(name, feeder, side_effects, url="v4"):
    return goldens.run_case(name, *feeder, side_effects, url=url)


@pytest.mark.parametrize("name", goldens.case_ids())
def test_golden(name, feeder, side_effects):
    actual = _run(name, feeder, side_effects)
    goldens.check_golden(name, actual)


def test_golden_count():
    ids = goldens.case_ids()
    assert len(goldens.load_manifest()) == 55
    assert len([i for i in ids if i.endswith("+flag")]) == 10


def test_v3_url_gives_the_same_golden_as_v4(feeder, side_effects):
    actual = _run("x27-L7", feeder, side_effects, url="v3")
    expected = goldens.load_golden("x27-L7")
    actual["request"] = expected["request"]
    assert {"key": "x27-L7", **actual} == expected


def _post(name, feeder):
    node, api_key = feeder
    entry = goldens.entry_for(name)
    return goldens.post_wire(goldens.load_wire(name), node, api_key, feeder_num=entry["feeder_num"])


def test_same_replay_id_with_new_hops_is_one_packet_and_one_observation(feeder, side_effects):
    assert _post("x28-L4", feeder).status_code == 201
    assert _post("x28h4-L4", feeder).status_code == 201

    assert MtRawPacket.objects.count() == 1
    observation = PacketObservation.objects.get()
    assert (observation.hop_start, observation.hop_limit) == (3, 3)  # first wins


def test_posting_a_replay_twice_adds_no_rows(feeder, side_effects):
    assert _post("x28-L4", feeder).status_code == 201
    assert _post("x28-L4", feeder).status_code == 201

    assert MtRawPacket.objects.count() == 1
    assert PacketObservation.objects.count() == 1


def test_replay_after_a_live_position_changes_neither_last_heard_nor_status(feeder, side_effects):
    sender = goldens.load_wire("x28-L4")["from"]
    live = goldens.load_wire("x28-L81")
    live["from"] = sender
    live["fromId"] = None
    node, api_key = feeder
    response = goldens.post_wire(live, node, api_key, feeder_num=3769067321)
    assert response.status_code == 201

    before = ObservedNode.objects.get(meshtastic_node_id=sender)
    status_before = NodeLatestStatus.objects.get(node=before)
    status_fields = goldens._field_values(status_before, {"id", "node"})
    last_heard = before.last_heard
    assert last_heard is not None and last_heard <= timezone.now()

    assert _post("x28-L4", feeder).status_code == 201

    after = ObservedNode.objects.get(meshtastic_node_id=sender)
    assert after.last_heard == last_heard
    assert goldens._field_values(NodeLatestStatus.objects.get(node=after), {"id", "node"}) == status_fields
    assert PacketObservation.objects.filter(replayed=True).count() == 1
