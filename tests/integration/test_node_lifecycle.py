"""
Integration tests for ObservedNode lifecycle behavior.

Verifies node creation, inference, updates, and claim flow as specified in docs/NODE_LIFECYCLE.md.
"""

import copy
import random

from .conftest import load_fixture


def _expected_node_id_str(node_id: int) -> str:
    """Compute expected node_id_str from node_id (matches mesh_node_helpers.meshtastic_id_to_hex)."""
    return f"!{node_id & 0xFFFFFFFF:08x}"


def test_device_metrics_creates_observed_node(api_client):
    """Ingesting a device metrics packet should create ObservedNode for the sender."""
    payload = load_fixture("TELEMETRY_APP/device_metrics.json")
    payload = copy.deepcopy(payload)
    from_int = 7777888899
    payload["from"] = from_int
    payload["id"] = 1111222333444

    resp = api_client.post_ingest(payload)
    assert resp.status_code == 201

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200
    node_data = node_resp.json()
    assert node_data["node_id"] == from_int


def test_node_info_creates_observed_node(api_client):
    """Ingesting a node info packet should create ObservedNode with correct names."""
    payload = load_fixture("NODE_LIFECYCLE/inferred_node_nodeinfo.json")
    payload = copy.deepcopy(payload)
    from_int = 2222333444
    payload["from"] = from_int
    payload["decoded"]["user"]["id"] = f"!{from_int & 0xFFFFFFFF:08x}"
    payload["id"] = 8888777668
    user = payload["decoded"]["user"]

    resp = api_client.post_ingest(payload)
    assert resp.status_code == 201

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200
    node_data = node_resp.json()
    assert node_data["node_id"] == from_int
    assert node_data["long_name"] == user["longName"]
    assert node_data["short_name"] == user["shortName"]


def test_text_message_creates_observed_node(api_client):
    """Ingesting a text message packet should create ObservedNode for the sender."""
    payload = load_fixture("TEXT_MESSAGE_APP/minimal.json")
    payload = copy.deepcopy(payload)
    from_int = 8888999000
    payload["from"] = from_int
    payload["id"] = 2222333444555

    resp = api_client.post_ingest(payload)
    assert resp.status_code == 201

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200
    node_data = node_resp.json()
    assert node_data["node_id"] == from_int


def test_inferred_node_has_placeholder_names(api_client):
    """When first packet is not NodeInfo, node is created with placeholder names."""
    payload = load_fixture("NODE_LIFECYCLE/inferred_node_position.json")
    payload = copy.deepcopy(payload)
    from_int = 1111222230
    payload["from"] = from_int
    payload["fromId"] = _expected_node_id_str(from_int)
    payload["id"] = 8888777669
    expected_node_id_str = _expected_node_id_str(from_int)

    resp = api_client.post_ingest(payload)
    assert resp.status_code == 201

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200
    node_data = node_resp.json()
    # long_name: "Unknown Node !xxx" per docs, or node_id_str in some implementations
    assert node_data["long_name"] in (
        f"Unknown Node {expected_node_id_str}",
        expected_node_id_str,
    )
    assert node_data["short_name"] == expected_node_id_str[-4:]
    assert node_data["node_id_str"] == expected_node_id_str


def test_node_info_updates_inferred_node(api_client):
    """NodeInfo packet after inferred node should update long_name, short_name, hw_model, etc."""
    pos_payload = load_fixture("NODE_LIFECYCLE/inferred_node_position.json")
    nodeinfo_payload = load_fixture("NODE_LIFECYCLE/inferred_node_nodeinfo.json")
    from_int = pos_payload["from"]
    user = nodeinfo_payload["decoded"]["user"]

    resp1 = api_client.post_ingest(pos_payload)
    assert resp1.status_code == 201

    resp2 = api_client.post_ingest(nodeinfo_payload)
    assert resp2.status_code == 201

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200
    node_data = node_resp.json()
    assert node_data["long_name"] == user["longName"]
    assert node_data["short_name"] == user["shortName"]
    assert node_data["hw_model"] == user["hwModel"]
    assert node_data.get("sw_version") == user.get("swVersion")
    assert node_data["role"] is not None
    assert node_data.get("public_key") == user.get("publicKey")


def test_node_id_str_inferred_from_from_int(api_client):
    """node_id_str should be inferred from from_int when fromId is omitted."""
    payload = load_fixture("NODE_LIFECYCLE/node_id_str_position.json")
    from_int = payload["from"]
    expected_node_id_str = _expected_node_id_str(from_int)

    resp = api_client.post_ingest(payload)
    assert resp.status_code == 201

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200
    node_data = node_resp.json()
    assert node_data["node_id_str"] == expected_node_id_str
    assert node_data["node_id"] == from_int


def test_last_heard_updated_on_packet(api_client):
    """Ingesting a packet should update last_heard on the ObservedNode."""
    payload = load_fixture("NODE_LIFECYCLE/inferred_node_position.json")
    from_int = payload["from"]

    resp = api_client.post_ingest(payload)
    assert resp.status_code == 201

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200
    node_data = node_resp.json()
    assert node_data["last_heard"] is not None
    last_heard_str = node_data["last_heard"]
    assert isinstance(last_heard_str, str) and len(last_heard_str) > 0


def test_device_metrics_updates_node_latest_status(api_client):
    """Ingesting device metrics should update NodeLatestStatus (latest_device_metrics)."""
    payload = load_fixture("TELEMETRY_APP/device_metrics.json")
    payload = copy.deepcopy(payload)
    from_int = 9999000111
    payload["from"] = from_int
    payload["id"] = 3333444555666
    device_metrics = payload["decoded"]["telemetry"]["deviceMetrics"]

    resp = api_client.post_ingest(payload)
    assert resp.status_code == 201

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200
    node_data = node_resp.json()
    latest = node_data.get("latest_device_metrics")
    assert latest is not None
    assert latest.get("battery_level") == device_metrics["batteryLevel"]
    assert latest.get("voltage") == device_metrics["voltage"]


def test_node_claim_via_direct_message(api_client):
    """Node claim: create claim, ingest direct message with claim key, verify claimed_by."""
    pos_payload = load_fixture("NODE_LIFECYCLE/claim_node_position.json")
    msg_payload = load_fixture("NODE_LIFECYCLE/claim_direct_message_template.json")
    # Use unique node_id to avoid "Claim already exists" from previous runs
    from_int = 500000000 + random.randint(0, 99999999)
    pos_payload = copy.deepcopy(pos_payload)
    pos_payload["from"] = from_int
    pos_payload["fromId"] = _expected_node_id_str(from_int)
    pos_payload["id"] = 7777888999

    resp_pos = api_client.post_ingest(pos_payload)
    assert resp_pos.status_code == 201

    claim_resp = api_client.post_claim(from_int)
    assert claim_resp.status_code == 201
    claim_data = claim_resp.json()
    claim_key = claim_data["claim_key"]
    assert claim_key

    msg_payload = copy.deepcopy(msg_payload)
    msg_payload["from"] = from_int
    msg_payload["fromId"] = _expected_node_id_str(from_int)
    msg_payload["decoded"]["text"] = claim_key
    msg_payload["id"] = 4444555666777

    resp_msg = api_client.post_ingest(msg_payload)
    assert resp_msg.status_code == 201

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200
    node_data = node_resp.json()
    assert node_data.get("owner") is not None
    assert node_data["owner"]["username"] == "integration-test@example.com"
