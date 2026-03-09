"""
Pytest fixtures for integration tests.

Expects:
- MESHFLOW_API_URL: Base URL (e.g. http://localhost:8000 or http://api:8000)
- MESHFLOW_NODE_API_KEY: API key for packet ingest (from seed_integration_tests)
- MESHFLOW_TEST_USERNAME: Username for JWT (default: integration-test@example.com)
- MESHFLOW_TEST_PASSWORD: Password for JWT (default: integration-test-password)
"""

import os
import time
from pathlib import Path

import pytest
import requests

# Observer node_ids from seed_integration_tests
OBSERVER_NODE_ID = 999999999
OBSERVER_NODE_ID_2 = 999999998


def get_api_url():
    return os.environ.get("MESHFLOW_API_URL", "http://localhost:8000")


def get_node_api_key():
    key = os.environ.get("MESHFLOW_NODE_API_KEY", "integration-test-key-a1b2c3d4e5f6")
    if not key:
        pytest.skip("MESHFLOW_NODE_API_KEY not set")
    return key


def get_jwt_credentials():
    return {
        "username": os.environ.get(
            "MESHFLOW_TEST_USERNAME", "integration-test@example.com"
        ),
        "password": os.environ.get(
            "MESHFLOW_TEST_PASSWORD", "integration-test-password"
        ),
    }


@pytest.fixture(scope="session")
def api_base_url():
    return get_api_url().rstrip("/")


@pytest.fixture(scope="session")
def wait_for_api(api_base_url):
    """Wait for API to be ready (used by session-scoped fixtures)."""
    url = f"{api_base_url}/api/status/"
    for _ in range(30):
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    pytest.fail(f"API not ready at {url} after 30s")


@pytest.fixture(scope="session")
def jwt_token(api_base_url, wait_for_api):
    """Obtain JWT for authenticated API calls (observed nodes, etc.)."""
    url = f"{api_base_url}/api/token/"
    creds = get_jwt_credentials()
    r = requests.post(url, json=creds, timeout=10)
    if r.status_code != 200:
        pytest.fail(
            f"Failed to obtain JWT: {r.status_code} {r.text}. "
            "Run 'python manage.py seed_integration_tests' (or 'docker compose run --rm api python manage.py seed_integration_tests') first."
        )
    data = r.json()
    return data["access"]


@pytest.fixture
def api_client(api_base_url, wait_for_api, jwt_token):
    """HTTP client with helpers for ingest (NodeAPIKey) and read (JWT) operations."""
    node_key = get_node_api_key()

    class Client:
        def __init__(self):
            self.base = api_base_url
            self.node_key = node_key
            self.jwt = jwt_token

        def post_ingest(self, payload, observer_node_id=OBSERVER_NODE_ID):
            url = f"{self.base}/api/packets/{observer_node_id}/ingest/"
            return requests.post(
                url,
                json=payload,
                headers={
                    "X-API-KEY": self.node_key,
                    "Content-Type": "application/json",
                },
                timeout=10,
            )

        def get_observed_node(self, node_id):
            url = f"{self.base}/api/nodes/observed-nodes/{node_id}/"
            return requests.get(
                url,
                headers={"Authorization": f"Bearer {self.jwt}"},
                timeout=10,
            )

        def get_positions(self, node_id):
            url = f"{self.base}/api/nodes/observed-nodes/{node_id}/positions/"
            return requests.get(
                url,
                headers={"Authorization": f"Bearer {self.jwt}"},
                timeout=10,
            )

        def get_device_metrics(self, node_id):
            url = f"{self.base}/api/nodes/observed-nodes/{node_id}/device_metrics/"
            return requests.get(
                url,
                headers={"Authorization": f"Bearer {self.jwt}"},
                timeout=10,
            )

        def search_nodes(self, q):
            url = f"{self.base}/api/nodes/observed-nodes/search/"
            return requests.get(
                url,
                params={"q": q},
                headers={"Authorization": f"Bearer {self.jwt}"},
                timeout=10,
            )

        def post_claim(self, node_id):
            """Create a NodeOwnerClaim for the given node. Returns response with claim_key."""
            url = f"{self.base}/api/nodes/observed-nodes/{node_id}/claim/"
            return requests.post(
                url,
                headers={"Authorization": f"Bearer {self.jwt}"},
                timeout=10,
            )

    return Client()


def load_fixture(relative_path):
    """Load a JSON fixture from tests/fixtures/."""
    fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures"
    path = fixtures_dir / relative_path
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    import json

    with open(path) as f:
        return json.load(f)


@pytest.fixture
def load_packet_fixture():
    return load_fixture
