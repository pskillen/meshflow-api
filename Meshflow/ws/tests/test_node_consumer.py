"""Tests for NodeConsumer."""

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

import Meshflow.routing  # noqa: F401 - ensure routing is loaded

application = URLRouter(Meshflow.routing.websocket_urlpatterns)


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_node_consumer_rejects_missing_api_key(node_auth_data):
    """Connection without api_key is rejected."""
    await database_sync_to_async(node_auth_data)()
    communicator = WebsocketCommunicator(application, "/ws/nodes/")
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_node_consumer_rejects_invalid_api_key(node_auth_data):
    """Connection with invalid api_key is rejected."""
    await database_sync_to_async(node_auth_data)()
    communicator = WebsocketCommunicator(application, "/ws/nodes/?api_key=invalid-key-12345")
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_node_consumer_accepts_valid_api_key(node_auth_data):
    """Connection with valid NodeAPIKey is accepted."""
    data = await database_sync_to_async(node_auth_data)()
    communicator = WebsocketCommunicator(application, f"/ws/nodes/?api_key={data['api_key']}")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_node_consumer_receives_traceroute_command(node_auth_data):
    """When channel layer sends node_command, client receives the command JSON."""
    from channels.layers import get_channel_layer

    data = await database_sync_to_async(node_auth_data)()
    communicator = WebsocketCommunicator(application, f"/ws/nodes/?api_key={data['api_key']}")
    connected, _ = await communicator.connect()
    assert connected is True

    # Send traceroute command via channel layer (simulating trigger API)
    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        f"node_{data['node_id']}",
        {"type": "node_command", "command": {"type": "traceroute", "target": 1623194643}},
    )

    # Client should receive the command
    response = await communicator.receive_json_from()
    assert response == {"type": "traceroute", "target": 1623194643}

    await communicator.disconnect()
