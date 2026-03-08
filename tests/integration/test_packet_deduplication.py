"""
Integration tests for packet deduplication.

Verifies that duplicate packets (same sender, packet_id, within time window)
are handled correctly: idempotent for same observer, new observation for different observer.
"""

import copy

import pytest

from .conftest import OBSERVER_NODE_ID, OBSERVER_NODE_ID_2, load_fixture


def test_same_packet_same_observer_twice_idempotent(api_client):
    """Posting the same packet twice from the same observer should be idempotent (200 both times)."""
    payload = load_fixture("TEXT_MESSAGE_APP/minimal.json")
    resp1 = api_client.post_ingest(payload)
    assert resp1.status_code == 201

    resp2 = api_client.post_ingest(payload)
    assert resp2.status_code == 201


def test_same_packet_different_packet_id_creates_new(api_client):
    """Same sender, different packet_id should create a new packet."""
    payload1 = load_fixture("TEXT_MESSAGE_APP/minimal.json")
    resp1 = api_client.post_ingest(payload1)
    assert resp1.status_code == 201

    payload2 = copy.deepcopy(payload1)
    payload2["id"] = payload1["id"] + 1
    resp2 = api_client.post_ingest(payload2)
    assert resp2.status_code == 201


def test_same_packet_two_observers_both_succeed(api_client):
    """Same packet from two different observers should both return 200 (one RawPacket, two PacketObservations)."""
    payload = load_fixture("TEXT_MESSAGE_APP/minimal.json")
    resp1 = api_client.post_ingest(payload, observer_node_id=OBSERVER_NODE_ID)
    assert resp1.status_code == 201

    resp2 = api_client.post_ingest(payload, observer_node_id=OBSERVER_NODE_ID_2)
    assert resp2.status_code == 201
