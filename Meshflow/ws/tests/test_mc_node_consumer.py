"""MeshCore NodeConsumer WebSocket tests."""

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

import Meshflow.routing  # noqa: F401
from common.protocol import Protocol
from common.ws_groups import managed_node_ws_group

application = URLRouter(Meshflow.routing.websocket_urlpatterns)

FEEDER_PUBKEY = "1a37f5aea4a1" + ("b" * 52)
FEEDER_PREFIX = "1a37f5aea4a1"


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mc_consumer_requires_prefix_when_multiple_feeders(create_managed_node, create_node_api_key):
    from nodes.models import NodeAuth

    @database_sync_to_async
    def setup():
        constellation = create_managed_node(protocol=Protocol.MESHCORE).constellation
        node_a = create_managed_node(
            meshtastic_node_id=0,
            protocol=Protocol.MESHCORE,
            constellation=constellation,
            mc_pubkey=FEEDER_PUBKEY,
        )
        node_b = create_managed_node(
            meshtastic_node_id=0,
            protocol=Protocol.MESHCORE,
            constellation=constellation,
            mc_pubkey="c" * 64,
        )
        api_key = create_node_api_key(constellation=constellation)
        NodeAuth.objects.create(api_key=api_key, node=node_a)
        NodeAuth.objects.create(api_key=api_key, node=node_b)
        return api_key.key

    api_key = await setup()
    communicator = WebsocketCommunicator(
        application,
        f"/ws/nodes/?api_key={api_key}",
    )
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mc_consumer_accepts_feeder_pubkey_prefix(create_managed_node, create_node_api_key):
    from channels.layers import get_channel_layer

    from nodes.models import NodeAuth

    @database_sync_to_async
    def setup():
        node = create_managed_node(
            meshtastic_node_id=0,
            protocol=Protocol.MESHCORE,
            mc_pubkey=FEEDER_PUBKEY,
        )
        api_key = create_node_api_key(constellation=node.constellation)
        NodeAuth.objects.create(api_key=api_key, node=node)
        return {
            "api_key": api_key.key,
            "group": managed_node_ws_group(node),
        }

    data = await setup()
    url = f"/ws/nodes/?api_key={data['api_key']}&feeder_pubkey_prefix={FEEDER_PREFIX}"
    communicator = WebsocketCommunicator(application, url)
    connected, _ = await communicator.connect()
    assert connected is True

    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        data["group"],
        {
            "type": "node_command",
            "command": {"type": "apply_mc_channel_config", "channels": []},
        },
    )
    response = await communicator.receive_json_from()
    assert response["type"] == "apply_mc_channel_config"

    await channel_layer.group_send(
        data["group"],
        {
            "type": "node_command",
            "command": {"type": "refresh_feeder_config"},
        },
    )
    response = await communicator.receive_json_from()
    assert response["type"] == "refresh_feeder_config"

    await communicator.disconnect()
