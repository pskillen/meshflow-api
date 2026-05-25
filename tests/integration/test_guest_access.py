"""Integration-style tests for anonymous guest API access (no JWT)."""

import pytest
import requests

BASE = "http://127.0.0.1:8000/api"


@pytest.mark.integration
def test_guest_constellations_list():
    resp = requests.get(f"{BASE}/constellations/", timeout=10)
    assert resp.status_code == 200
    assert "results" in resp.json()


@pytest.mark.integration
def test_guest_observed_nodes_list():
    resp = requests.get(f"{BASE}/nodes/observed-nodes/", timeout=10)
    assert resp.status_code == 200


@pytest.mark.integration
def test_guest_traceroutes_list():
    resp = requests.get(f"{BASE}/traceroutes/", timeout=10)
    assert resp.status_code == 200
