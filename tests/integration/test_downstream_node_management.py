"""
Integration tests for node info packet downstream effects.

Verifies that ingesting node info packets creates/updates ObservedNode with name, hw_model, etc.
"""

from .conftest import load_fixture


def test_node_info_packet_updates_observed_node(api_client):
    """Ingesting a node info packet should create/update ObservedNode with name, hw_model, etc."""
    payload = load_fixture("NODEINFO_APP/minimal.json")
    from_int = payload["from"]
    user = payload["decoded"]["user"]

    resp = api_client.post_ingest(payload)
    assert resp.status_code == 201

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200
    node_data = node_resp.json()
    assert node_data["node_id"] == from_int
    assert node_data["long_name"] == user["longName"]
    assert node_data["short_name"] == user["shortName"]
    assert node_data["hw_model"] == user["hwModel"]
