"""
Pytest fixtures for integration tests.

Expects:
- MESHFLOW_API_URL: Base URL (e.g. http://localhost:8000 or http://api:8000)
- MESHFLOW_NODE_API_KEY: API key for packet ingest (from seed_integration_tests)
- MESHFLOW_TEST_USERNAME: Username for JWT (default: integration-test@example.com)
- MESHFLOW_TEST_PASSWORD: Password for JWT (default: integration-test-password)
"""

import os
import re
import time
from pathlib import Path

import pytest
import requests

_OBSERVED_NODE_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Observer node_ids from seed_integration_tests
OBSERVER_NODE_ID = 999999999
OBSERVER_NODE_ID_2 = 999999998

# device_metrics history can be large/slow on a long-lived local DB
INTEGRATION_HTTP_TIMEOUT = int(os.environ.get("MESHFLOW_INTEGRATION_TIMEOUT", "45"))


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

        def _auth_headers(self):
            return {"Authorization": f"Bearer {self.jwt}"}

        @staticmethod
        def _is_meshtastic_node_id(node_id):
            if isinstance(node_id, int):
                return True
            return isinstance(node_id, str) and node_id.isdigit()

        @staticmethod
        def _is_internal_id(node_id):
            return isinstance(node_id, str) and bool(_OBSERVED_NODE_UUID_RE.match(node_id))

        def resolve_internal_id(self, node_id):
            """Map meshtastic_node_id (int) to ObservedNode.internal_id (UUID string)."""
            if self._is_internal_id(node_id):
                return node_id
            if self._is_meshtastic_node_id(node_id):
                r = self.get_observed_node(int(node_id))
                if r.status_code != 200:
                    raise AssertionError(
                        f"Could not resolve meshtastic_node_id {node_id}: {r.status_code} {r.text}"
                    )
                return r.json()["internal_id"]
            raise ValueError(f"Not a meshtastic_node_id or internal_id: {node_id!r}")

        def post_ingest(self, payload, observer_node_id=OBSERVER_NODE_ID):
            url = f"{self.base}/api/packets/{observer_node_id}/ingest/"
            return requests.post(
                url,
                json=payload,
                headers={
                    "X-API-KEY": self.node_key,
                    "Content-Type": "application/json",
                },
                timeout=INTEGRATION_HTTP_TIMEOUT,
            )

        def get_observed_node(self, node_id):
            if self._is_meshtastic_node_id(node_id):
                url = f"{self.base}/api/nodes/observed-nodes/by-meshtastic-id/{int(node_id)}/"
                return requests.get(
                    url,
                    headers=self._auth_headers(),
                    allow_redirects=True,
                    timeout=INTEGRATION_HTTP_TIMEOUT,
                )
            url = f"{self.base}/api/nodes/observed-nodes/{node_id}/"
            return requests.get(
                url,
                headers=self._auth_headers(),
                timeout=INTEGRATION_HTTP_TIMEOUT,
            )

        def get_positions(self, node_id):
            internal_id = self.resolve_internal_id(node_id)
            url = f"{self.base}/api/nodes/observed-nodes/{internal_id}/positions/"
            return requests.get(
                url,
                headers=self._auth_headers(),
                timeout=INTEGRATION_HTTP_TIMEOUT,
            )

        def get_device_metrics(self, node_id):
            internal_id = self.resolve_internal_id(node_id)
            url = f"{self.base}/api/nodes/observed-nodes/{internal_id}/device_metrics/"
            return requests.get(
                url,
                headers=self._auth_headers(),
                timeout=INTEGRATION_HTTP_TIMEOUT,
            )

        def search_nodes(self, q):
            url = f"{self.base}/api/nodes/observed-nodes/search/"
            return requests.get(
                url,
                params={"q": q},
                headers={"Authorization": f"Bearer {self.jwt}"},
                timeout=INTEGRATION_HTTP_TIMEOUT,
            )

        def post_claim(self, node_id):
            """Create a NodeOwnerClaim for the given node. Returns response with claim_key."""
            internal_id = self.resolve_internal_id(node_id)
            url = f"{self.base}/api/nodes/observed-nodes/{internal_id}/claim/"
            return requests.post(
                url,
                headers=self._auth_headers(),
                timeout=INTEGRATION_HTTP_TIMEOUT,
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
