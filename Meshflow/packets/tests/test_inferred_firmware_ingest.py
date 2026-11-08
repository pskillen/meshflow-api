"""Firmware generation inferred on ingest: NODEINFO, NodeDB upserts and by-number creation.

The wire bodies are the capture goldens (``docs/packets/meshtastic-2.8``); ``sender-id:crc32`` NODEINFO is a 2.8
sender, ``sender-id:mac`` is 2.7 or earlier.
"""

import itertools

from django.urls import reverse

import pytest
from rest_framework.test import APIClient

from common.meshtastic_identity import key_node_id
from nodes.models import ObservedNode
from packets.tests import goldens

pytestmark = pytest.mark.django_db

FEEDER_NUM = 3769067321
# A real key and the number it derives (the worked example: !da545c78 -> !4396524c).
KEY = "oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs="
OLD_NUM = 0xDA545C78
NEW_NUM = 0x4396524C
# The wild 2.8 sender in x28-L85: its number is the crc32 of its key.
L85_KEY = goldens.load_wire("x28-L85")["decoded"]["user"]["publicKey"]
L85_NUM = goldens.load_wire("x28-L85")["from"]

NODEINFO_CASES = [
    (entry["key"], "2.8" if "sender-id:crc32" in entry["labels"] else "2.7")
    for entry in goldens.load_manifest()
    if "port:NODEINFO_APP" in entry["labels"]
]
REPLAY_KEYS = [entry["key"] for entry in goldens.load_manifest() if entry["kind"] == "replay"]

_ids = itertools.count(4_000_000_000)


def fields(num):
    node = ObservedNode.objects.get(meshtastic_node_id=num)
    return node.inferred_firmware, node.inferred_firmware_basis


def stamp(num):
    return ObservedNode.objects.get(meshtastic_node_id=num).inferred_firmware_at


def nodeinfo_wire(num, key):
    body = goldens.load_wire("x28-L85")
    body["from"] = num
    body["fromId"] = None
    body["id"] = next(_ids)
    body["decoded"]["user"]["publicKey"] = key
    return body


def position_wire(num):
    body = goldens.load_wire("x27-L7")
    body["from"] = num
    body["fromId"] = None
    body["id"] = next(_ids)
    return body


def post(feeder, body):
    node, api_key = feeder
    response = goldens.post_wire(body, node, api_key, feeder_num=FEEDER_NUM)
    assert response.status_code == 201, response.content
    return response


def upsert(feeder, num, **data):
    _, api_key = feeder
    response = APIClient().post(
        reverse("feeder-v4-meshtastic-nodes"), {"id": num, **data}, format="json", HTTP_X_API_KEY=api_key.key
    )
    assert response.status_code == 200, response.content


def test_fixture_numbers_are_what_the_tests_assume():
    assert key_node_id(KEY) == NEW_NUM
    assert key_node_id(L85_KEY) == L85_NUM


@pytest.mark.parametrize("name, generation", NODEINFO_CASES)
def test_nodeinfo_capture_is_classified_from_its_label(name, generation, feeder, side_effects):
    body = goldens.load_wire(name)
    goldens.run_case(name, *feeder, side_effects)

    assert fields(body["from"]) == (generation, "key_identity")
    assert stamp(body["from"]) is not None


def test_manifest_has_both_kinds_of_nodeinfo():
    assert {generation for _, generation in NODEINFO_CASES} == {"2.7", "2.8"}
    assert len(NODEINFO_CASES) == 5


@pytest.mark.parametrize("num, expected", [(NEW_NUM, "2.8"), (OLD_NUM, "2.7")])
def test_every_arrival_order_gives_the_same_verdict(num, expected, feeder, side_effects):
    steps = {
        "nodeinfo": lambda: post(feeder, nodeinfo_wire(num, KEY)),
        "upsert": lambda: upsert(feeder, num, meshtastic_public_key=KEY, long_name="NodeDB name"),
        "position": lambda: post(feeder, position_wire(num)),
    }
    results = set()
    for order in itertools.permutations(steps):
        ObservedNode.objects.filter(meshtastic_node_id=num).delete()
        for step in order:
            steps[step]()
        results.add(fields(num))
    assert results == {(expected, "key_identity")}


def test_predicted_when_key_holder_arrives_first(feeder, side_effects):
    post(feeder, nodeinfo_wire(OLD_NUM, KEY))
    assert fields(OLD_NUM) == ("2.7", "key_identity")

    post(feeder, position_wire(NEW_NUM))

    assert fields(NEW_NUM) == ("2.8", "predicted_id")


def test_predicted_when_keyless_row_arrives_first(feeder, side_effects):
    post(feeder, position_wire(NEW_NUM))
    assert fields(NEW_NUM) == (None, None)

    post(feeder, nodeinfo_wire(OLD_NUM, KEY))

    assert fields(NEW_NUM) == ("2.8", "predicted_id")


def test_predicted_when_key_arrives_by_nodedb_upsert(feeder, side_effects):
    post(feeder, position_wire(NEW_NUM))

    upsert(feeder, OLD_NUM, meshtastic_public_key=KEY)

    assert fields(OLD_NUM) == ("2.7", "key_identity")
    assert fields(NEW_NUM) == ("2.8", "predicted_id")


def test_predicted_row_is_upgraded_by_its_own_key(feeder, side_effects):
    post(feeder, nodeinfo_wire(0x1234, L85_KEY))
    post(feeder, position_wire(L85_NUM))
    assert fields(L85_NUM) == ("2.8", "predicted_id")

    post(feeder, nodeinfo_wire(L85_NUM, L85_KEY))

    assert fields(L85_NUM) == ("2.8", "key_identity")


@pytest.mark.parametrize("name", REPLAY_KEYS)
def test_replays_leave_a_classified_row_untouched(name, feeder, side_effects):
    post(feeder, nodeinfo_wire(L85_NUM, L85_KEY))
    before = (fields(L85_NUM), stamp(L85_NUM))
    body = goldens.load_wire(name)
    body["from"] = L85_NUM
    body["fromId"] = None

    node, api_key = feeder
    goldens.post_wire(body, node, api_key, feeder_num=goldens.entry_for(name)["feeder_num"])
    goldens.post_wire(body, node, api_key, feeder_num=goldens.entry_for(name)["feeder_num"])

    assert (fields(L85_NUM), stamp(L85_NUM)) == before


def test_reclassifying_the_same_verdict_keeps_the_stamp(feeder, side_effects):
    post(feeder, nodeinfo_wire(OLD_NUM, KEY))
    first = stamp(OLD_NUM)

    post(feeder, nodeinfo_wire(OLD_NUM, KEY))
    upsert(feeder, OLD_NUM, meshtastic_public_key=KEY)

    assert stamp(OLD_NUM) == first


def test_position_from_a_new_sender_has_no_evidence(feeder, side_effects):
    post(feeder, position_wire(0x0BADF00D))

    assert fields(0x0BADF00D) == (None, None)
    assert stamp(0x0BADF00D) is None


@pytest.mark.parametrize("blank", ["", None])
def test_nodeinfo_without_a_key_is_not_evidence(blank, feeder, side_effects):
    body = nodeinfo_wire(0x0BADF00D, blank)
    if blank is None:
        del body["decoded"]["user"]["publicKey"]
    post(feeder, body)

    assert fields(0x0BADF00D) == (None, None)


def test_keyless_nodeinfo_does_not_clear_a_known_verdict(feeder, side_effects):
    post(feeder, nodeinfo_wire(OLD_NUM, KEY))
    post(feeder, nodeinfo_wire(OLD_NUM, ""))

    assert fields(OLD_NUM) == ("2.7", "key_identity")


def test_malformed_key_does_not_clear_a_known_verdict(feeder, side_effects):
    post(feeder, nodeinfo_wire(NEW_NUM, KEY))
    assert fields(NEW_NUM) == ("2.8", "key_identity")

    upsert(feeder, NEW_NUM, meshtastic_public_key="short")

    assert fields(NEW_NUM) == ("2.8", "key_identity")
