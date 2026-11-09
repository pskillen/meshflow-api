"""G17: after a feeder re-key the WebSocket still resolves the same ManagedNode (ID-4)."""

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

import Meshflow.routing  # noqa: F401
from common.protocol import Protocol
from nodes.models import ManagedNode, NodeAuth
from nodes.services.feeder_identity import apply_reported_identity

application = URLRouter(Meshflow.routing.websocket_urlpatterns)

OLD_NUM = 0xDA545C78
NEW_NUM = 0x4396524C
KEY_B64 = "oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs="


async def _connects(url) -> bool:
    communicator = WebsocketCommunicator(application, url)
    connected, _ = await communicator.connect()
    if connected:
        await communicator.disconnect()
    return connected


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_ws_follows_rekey(settings, create_managed_node, create_node_api_key):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True

    @database_sync_to_async
    def setup():
        node = create_managed_node(meshtastic_node_id=OLD_NUM, protocol=Protocol.MESHTASTIC)
        api_key = create_node_api_key(owner=node.owner, constellation=node.constellation)
        NodeAuth.objects.create(api_key=api_key, node=node)
        return node.pk, api_key.key

    pk, key = await setup()
    assert await _connects(f"/ws/nodes/?api_key={key}&feeder_node_id={OLD_NUM}")
    assert await _connects(f"/ws/nodes/?api_key={key}&feeder_scoped=1")

    @database_sync_to_async
    def rekey():
        node = ManagedNode.objects.get(pk=pk)
        return apply_reported_identity(node, reported_node_num=NEW_NUM, reported_pubkey=KEY_B64)

    event = await rekey()
    assert event.outcome == "auto_updated"

    assert await _connects(f"/ws/nodes/?api_key={key}&feeder_node_id={NEW_NUM}")
    assert not await _connects(f"/ws/nodes/?api_key={key}&feeder_node_id={OLD_NUM}")
    assert await _connects(f"/ws/nodes/?api_key={key}&feeder_scoped=1")
    assert await database_sync_to_async(ManagedNode.objects.filter(pk=pk, meshtastic_node_id=NEW_NUM).exists)()
