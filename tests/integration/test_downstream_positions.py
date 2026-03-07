"""
Integration tests for position packet downstream effects.

Verifies that ingesting position packets creates/updates ObservedNode and Position.
"""

from .conftest import load_fixture


def test_position_packet_creates_observed_node_and_position(api_client):
    """Ingesting a position packet should create ObservedNode and Position."""
    payload = load_fixture("POSITION_APP/minimal.json")
    from_int = payload["from"]

    resp = api_client.post_ingest(payload)
    assert resp.status_code == 200

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200
    node_data = node_resp.json()
    assert node_data["node_id"] == from_int
    assert node_data["node_id_str"] == payload["fromId"]

    pos_resp = api_client.get_positions(from_int)
    assert pos_resp.status_code == 200
    positions = pos_resp.json()
    if isinstance(positions, dict) and "results" in positions:
        positions = positions["results"]
    assert isinstance(positions, list) and len(positions) >= 1
    pos = positions[0]
    assert "latitude" in pos or "latitude_i" in pos
    assert "longitude" in pos or "longitude_i" in pos
