"""
Integration tests for packet ingest endpoint.

Tests that each packet type can be ingested successfully via HTTP POST.
"""

import pytest

from .conftest import load_fixture

INGEST_FIXTURES = [
    ("TEXT_MESSAGE_APP/minimal.json", "TEXT_MESSAGE_APP"),
    ("TRACEROUTE_APP/minimal.json", "TRACEROUTE_APP"),
    ("TEXT_MESSAGE_APP/with_reply_emoji.json", "TEXT_MESSAGE_APP"),
    ("POSITION_APP/minimal.json", "POSITION_APP"),
    ("POSITION_APP/with_optional_fields.json", "POSITION_APP"),
    ("NODEINFO_APP/minimal.json", "NODEINFO_APP"),
    ("TELEMETRY_APP/device_metrics.json", "TELEMETRY_APP"),
    ("TELEMETRY_APP/local_stats.json", "TELEMETRY_APP"),
    ("TELEMETRY_APP/environment_metrics.json", "TELEMETRY_APP"),
    ("TELEMETRY_APP/air_quality_metrics.json", "TELEMETRY_APP"),
    ("TELEMETRY_APP/power_metrics.json", "TELEMETRY_APP"),
    ("TELEMETRY_APP/health_metrics.json", "TELEMETRY_APP"),
    ("TELEMETRY_APP/host_metrics.json", "TELEMETRY_APP"),
    ("TELEMETRY_APP/traffic_management_stats.json", "TELEMETRY_APP"),
]


@pytest.mark.parametrize("fixture_file,portnum", INGEST_FIXTURES)
def test_ingest_packet_returns_success(api_client, fixture_file, portnum):
    """Each packet type should ingest successfully and return 201."""
    payload = load_fixture(fixture_file)
    resp = api_client.post_ingest(payload)
    assert (
        resp.status_code == 201
    ), f"Expected 201 for {portnum}, got {resp.status_code}: {resp.text}"


def test_ingest_encrypted_packet_returns_304(api_client):
    """Encrypted packets should be skipped and return 304."""
    payload = load_fixture("TEXT_MESSAGE_APP/minimal.json")
    payload["encrypted"] = True
    resp = api_client.post_ingest(payload)
    assert resp.status_code == 304


def test_ingest_invalid_portnum_returns_400(api_client):
    """Unknown or invalid portnum should return 400."""
    payload = load_fixture("TEXT_MESSAGE_APP/minimal.json")
    payload["decoded"]["portnum"] = "UNKNOWN_APP"
    resp = api_client.post_ingest(payload)
    assert resp.status_code == 400
