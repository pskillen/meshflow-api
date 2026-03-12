"""Fixtures for WebSocket tests. Wraps sync ORM in database_sync_to_async for async tests."""

import pytest


@pytest.fixture
def node_auth_data(create_node_auth):
    """
    Returns (api_key, node_id) from a fresh NodeAuth, suitable for async tests.
    Call via: data = await sync_to_async(node_auth_data)()
    """

    def _get():
        node_auth = create_node_auth()
        return {"api_key": node_auth.api_key.key, "node_id": node_auth.node.node_id}

    return _get
