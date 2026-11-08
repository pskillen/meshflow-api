"""NodeConsumer with ``feeder_scoped=1``: the API key alone picks the feeder (v4 rule)."""

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

import Meshflow.routing  # noqa: F401
from common.protocol import Protocol

application = URLRouter(Meshflow.routing.websocket_urlpatterns)


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_feeder_scoped_single_key_joins_internal_id_group(create_managed_node, create_node_api_key):
    from nodes.models import NodeAuth

    @database_sync_to_async
    def setup():
        node = create_managed_node(protocol=Protocol.MESHTASTIC)
        api_key = create_node_api_key(constellation=node.constellation)
        NodeAuth.objects.create(api_key=api_key, node=node)
        return api_key.key, f"node_mt_{node.internal_id}"

    key, group = await setup()
    communicator = WebsocketCommunicator(application, f"/ws/nodes/?api_key={key}&feeder_scoped=1")
    connected, _ = await communicator.connect()
    assert connected is True

    await get_channel_layer().group_send(group, {"type": "node_command", "command": {"type": "ping"}})
    assert await communicator.receive_json_from() == {"type": "ping"}
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_feeder_scoped_shared_key_closes(create_managed_node, create_constellation, create_node_api_key):
    from nodes.models import NodeAuth

    @database_sync_to_async
    def setup():
        constellation = create_constellation(protocol=Protocol.MESHTASTIC)
        node_a = create_managed_node(constellation=constellation, name="A", meshtastic_node_id=3001)
        node_b = create_managed_node(constellation=constellation, name="B", meshtastic_node_id=3002)
        api_key = create_node_api_key(constellation=constellation)
        NodeAuth.objects.create(api_key=api_key, node=node_a)
        NodeAuth.objects.create(api_key=api_key, node=node_b)
        return api_key.key

    key = await setup()
    # Even with a disambiguator, feeder_scoped applies the single-feeder rule.
    communicator = WebsocketCommunicator(application, f"/ws/nodes/?api_key={key}&feeder_scoped=1&feeder_node_id=3001")
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_feeder_scoped_unlinked_key_closes(create_node_api_key):
    key = (await database_sync_to_async(create_node_api_key)()).key

    communicator = WebsocketCommunicator(application, f"/ws/nodes/?api_key={key}&feeder_scoped=1")
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_without_flag_shared_key_still_uses_node_id(
    create_managed_node, create_constellation, create_node_api_key
):
    from nodes.models import NodeAuth

    @database_sync_to_async
    def setup():
        constellation = create_constellation(protocol=Protocol.MESHTASTIC)
        node_a = create_managed_node(constellation=constellation, name="A", meshtastic_node_id=4001)
        node_b = create_managed_node(constellation=constellation, name="B", meshtastic_node_id=4002)
        api_key = create_node_api_key(constellation=constellation)
        NodeAuth.objects.create(api_key=api_key, node=node_a)
        NodeAuth.objects.create(api_key=api_key, node=node_b)
        return api_key.key

    key = await setup()
    communicator = WebsocketCommunicator(application, f"/ws/nodes/?api_key={key}&feeder_node_id=4001")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.disconnect()
