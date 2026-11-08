"""Unit tests for 2.8 connect-time replay detection (packets/replay.py)."""

from types import SimpleNamespace

from django.test import RequestFactory

import pytest

from packets.replay import feeder_node_nums, is_replayed_shape

FEEDER_OLD = 0x1A83CF89
FEEDER_NEW = 3769067321  # !e0a76739
OTHER = 52741281


def _replay(**overrides):
    data = {
        "from": OTHER,
        "to": 4294967295,
        "id": 3442272654,
        "rxTime": 1755078058,
        "rxSnr": 6.25,
        "priority": "BACKGROUND",
        "hopStart": 4,
        "transportMechanism": "TRANSPORT_LORA",
        "decoded": {"portnum": "POSITION_APP"},
    }
    data.update(overrides)
    return data


def test_full_shape_is_a_replay():
    assert is_replayed_shape(_replay(), {FEEDER_NEW}) is True


def test_null_rx_rssi_counts_as_absent():
    assert is_replayed_shape(_replay(rxRssi=None), {FEEDER_NEW}) is True


def test_int_enum_forms():
    assert is_replayed_shape(_replay(transportMechanism=1, priority=10), {FEEDER_NEW}) is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"rxRssi": -79},
        {"rxRssi": 0},
        {"transportMechanism": "TRANSPORT_MQTT"},
        {"viaMqtt": True},
        {"viaMqtt": True, "transportMechanism": "TRANSPORT_LORA"},
        {"transportMechanism": "TRANSPORT_MULTICAST_MQTT"},
        {"transportMechanism": 5},
        {"transportMechanism": None},
        {"transportMechanism": True},
        {"priority": "DEFAULT"},
        {"priority": 64},
        {"priority": None},
        {"from": None},
        {"from": "52741281"},
        {"from": FEEDER_NEW},
        {"from": FEEDER_OLD},
    ],
)
def test_each_missing_condition_is_not_a_replay(overrides):
    assert is_replayed_shape(_replay(**overrides), {FEEDER_OLD, FEEDER_NEW}) is False


def test_mqtt_packet_without_rssi_is_live():
    packet = _replay(viaMqtt=True)
    packet.pop("rxRssi", None)
    assert is_replayed_shape(packet, {FEEDER_OLD, FEEDER_NEW}) is False


def test_replay_shaped_lora_packet_is_still_replayed():
    assert is_replayed_shape(_replay(viaMqtt=False), {FEEDER_OLD, FEEDER_NEW}) is True
    assert is_replayed_shape(_replay(), {FEEDER_OLD, FEEDER_NEW}) is True


def test_missing_keys_are_not_a_replay():
    for key in ("transportMechanism", "priority", "from"):
        data = _replay()
        del data[key]
        assert is_replayed_shape(data, {FEEDER_NEW}) is False


def test_empty_feeder_set_is_never_a_replay():
    assert is_replayed_shape(_replay(), set()) is False


def test_feeder_nums_from_the_three_sources():
    observer = SimpleNamespace(meshtastic_node_id=FEEDER_OLD, reported_meshtastic_node_id=0x11112222)
    request = RequestFactory().post("/", HTTP_X_MESHTASTIC_FEEDER_NODE_NUM=str(FEEDER_NEW))
    nums = feeder_node_nums(observer, request)
    assert nums == {FEEDER_OLD, 0x11112222, FEEDER_NEW}
    for own in nums:
        assert is_replayed_shape(_replay(**{"from": own}), nums) is False


def test_feeder_nums_without_request_or_header():
    observer = SimpleNamespace(meshtastic_node_id=FEEDER_OLD, reported_meshtastic_node_id=None)
    assert feeder_node_nums(observer) == {FEEDER_OLD}
    assert feeder_node_nums(observer, RequestFactory().post("/")) == {FEEDER_OLD}
    bad = RequestFactory().post("/", HTTP_X_MESHTASTIC_FEEDER_NODE_NUM="nope")
    assert feeder_node_nums(observer, bad) == {FEEDER_OLD}


def test_feeder_nums_empty_when_nothing_known():
    observer = SimpleNamespace(meshtastic_node_id=None, reported_meshtastic_node_id=None)
    assert feeder_node_nums(observer) == set()
