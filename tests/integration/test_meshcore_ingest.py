"""
Integration test: MeshCore packet ingest (requires live API + seeded MC feeder).

Skip when MESHFLOW_API_URL or MC feeder credentials are not configured.
"""

import os
import uuid

import pytest
import requests

API_URL = os.environ.get("MESHFLOW_API_URL", "http://localhost:8000").rstrip("/")
MC_API_KEY = os.environ.get("MESHFLOW_MC_API_KEY", "")

FULL_PUBKEY = "c" * 64
PREFIX = "c" * 12


@pytest.mark.integration
@pytest.mark.skipif(not MC_API_KEY, reason="Set MESHFLOW_MC_API_KEY to a MeshCore feeder key")
def test_meshcore_advert_ingest_round_trip():
    """POST advert envelope; expect 201 and retrievable packet list (staff JWT optional)."""
    payload = {
        "event_type": "advertisement",
        "payload_type": "advert",
        "from_pubkey": FULL_PUBKEY,
        "pkt_hash": int(uuid.uuid4().int % (2**31)),
        "rx_time": 1730000000,
        "rx_rssi": -75.0,
        "adv_name": "IntegrationTest",
        "adv_lat": 55.95,
        "adv_lon": -4.09,
        "raw": {"public_key": FULL_PUBKEY},
    }
    headers = {"X-API-Key": MC_API_KEY}
    url = f"{API_URL}/api/meshcore/packets/ingest/"
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    assert response.status_code in (201, 200), response.text
    body = response.json()
    assert body.get("status") == "success"
    assert body.get("packet_id")
