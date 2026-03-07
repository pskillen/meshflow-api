"""
Integration tests for device metrics packet downstream effects.

Verifies that ingesting device metrics packets creates DeviceMetrics for the sender.
"""

from .conftest import load_fixture


def test_device_metrics_packet_creates_device_metrics(api_client):
    """Ingesting a device metrics packet should create DeviceMetrics for the sender."""
    payload = load_fixture("TELEMETRY_APP/device_metrics.json")
    from_int = payload["from"]

    resp = api_client.post_ingest(payload)
    assert resp.status_code == 201

    node_resp = api_client.get_observed_node(from_int)
    assert node_resp.status_code == 200

    metrics_resp = api_client.get_device_metrics(from_int)
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    if isinstance(metrics, dict) and "results" in metrics:
        metrics = metrics["results"]
    assert isinstance(metrics, list) and len(metrics) >= 1
