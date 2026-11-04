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
        data["group"],
        {"type": "node_command", "command": {"type": "traceroute", "target": 1623194643}},
    )

    # Client should receive the command
    response = await communicator.receive_json_from()
    assert response == {"type": "traceroute", "target": 1623194643}

    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_node_group_survives_meshtastic_node_id_change(node_auth_data):
    """A re-keyed feeder (new meshtastic_node_id) keeps the same group; the bot still gets commands."""
    from channels.layers import get_channel_layer

    from common.ws_groups import managed_node_ws_group
    from nodes.models import ManagedNode

    data = await database_sync_to_async(node_auth_data)()
    old_group = data["group"]
    assert old_group.startswith("node_mt_")

    @database_sync_to_async
    def rekey():
        node = ManagedNode.objects.get(meshtastic_node_id=data["node_id"])
        node.meshtastic_node_id = data["node_id"] + 1
        node.save(update_fields=["meshtastic_node_id"])
        return managed_node_ws_group(node)

    communicator = WebsocketCommunicator(application, f"/ws/nodes/?api_key={data['api_key']}")
    connected, _ = await communicator.connect()
    assert connected is True

    # Re-key while connected: a sender resolving the group afterwards still reaches the bot.
    assert await rekey() == old_group
    await get_channel_layer().group_send(
        old_group, {"type": "node_command", "command": {"type": "traceroute", "target": 5}}
    )
    assert await communicator.receive_json_from() == {"type": "traceroute", "target": 5}
    await communicator.disconnect()
