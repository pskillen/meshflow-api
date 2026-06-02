"""Meshtastic NodeConsumer WebSocket tests."""

import asyncio

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator

import Meshflow.routing  # noqa: F401
from common.protocol import Protocol
from common.ws_groups import managed_node_ws_group

application = URLRouter(Meshflow.routing.websocket_urlpatterns)

MT_NODE_A = 0x433B82F0
MT_NODE_B = 0x12345678

FEEDER_PUBKEY = "1a37f5aea4a1" + ("b" * 52)
FEEDER_PREFIX = "1a37f5aea4a1"


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mt_consumer_requires_node_id_when_multiple_feeders(
    create_managed_node, create_constellation, create_node_api_key
):
    from nodes.models import NodeAuth

    @database_sync_to_async
    def setup():
        constellation = create_constellation(protocol=Protocol.MESHTASTIC)
        node_a = create_managed_node(
            meshtastic_node_id=MT_NODE_A,
            protocol=Protocol.MESHTASTIC,
            constellation=constellation,
            name="Feeder A",
        )
        node_b = create_managed_node(
            meshtastic_node_id=MT_NODE_B,
            protocol=Protocol.MESHTASTIC,
            constellation=constellation,
            name="Feeder B",
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
async def test_mt_consumer_accepts_feeder_node_id(create_managed_node, create_node_api_key):
    from channels.layers import get_channel_layer

    from nodes.models import NodeAuth

    @database_sync_to_async
    def setup():
        node = create_managed_node(protocol=Protocol.MESHTASTIC)
        api_key = create_node_api_key(constellation=node.constellation)
        NodeAuth.objects.create(api_key=api_key, node=node)
        return {
            "api_key": api_key.key,
            "node_id": node.meshtastic_node_id,
            "group": managed_node_ws_group(node),
        }

    data = await setup()
    url = f"/ws/nodes/?api_key={data['api_key']}&feeder_node_id={data['node_id']}"
    communicator = WebsocketCommunicator(application, url)
    connected, _ = await communicator.connect()
    assert connected is True

    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        data["group"],
        {
            "type": "node_command",
            "command": {"type": "traceroute", "target": 1623194643},
        },
    )
    response = await communicator.receive_json_from()
    assert response == {"type": "traceroute", "target": 1623194643}

    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mt_consumer_accepts_feeder_node_id_str(create_managed_node, create_node_api_key):
    from common.mesh_node_helpers import meshtastic_id_to_hex
    from nodes.models import NodeAuth

    @database_sync_to_async
    def setup():
        node = create_managed_node(protocol=Protocol.MESHTASTIC)
        api_key = create_node_api_key(constellation=node.constellation)
        NodeAuth.objects.create(api_key=api_key, node=node)
        return api_key.key, meshtastic_id_to_hex(node.meshtastic_node_id)

    api_key, node_id_str = await setup()
    url = f"/ws/nodes/?api_key={api_key}&feeder_node_id_str={node_id_str}"
    communicator = WebsocketCommunicator(application, url)
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_two_mt_feeders_distinct_groups(create_managed_node, create_constellation, create_node_api_key):
    from channels.layers import get_channel_layer

    from nodes.models import NodeAuth

    @database_sync_to_async
    def setup():
        constellation = create_constellation(protocol=Protocol.MESHTASTIC)
        node_a = create_managed_node(
            protocol=Protocol.MESHTASTIC,
            constellation=constellation,
            name="Feeder A",
        )
        node_b = create_managed_node(
            protocol=Protocol.MESHTASTIC,
            constellation=constellation,
            name="Feeder B",
        )
        api_key = create_node_api_key(constellation=constellation)
        NodeAuth.objects.create(api_key=api_key, node=node_a)
        NodeAuth.objects.create(api_key=api_key, node=node_b)
        return {
            "api_key": api_key.key,
            "node_a_id": node_a.meshtastic_node_id,
            "node_b_id": node_b.meshtastic_node_id,
            "group_a": managed_node_ws_group(node_a),
            "group_b": managed_node_ws_group(node_b),
        }

    data = await setup()
    comm_a = WebsocketCommunicator(
        application,
        f"/ws/nodes/?api_key={data['api_key']}&feeder_node_id={data['node_a_id']}",
    )
    comm_b = WebsocketCommunicator(
        application,
        f"/ws/nodes/?api_key={data['api_key']}&feeder_node_id={data['node_b_id']}",
    )
    assert (await comm_a.connect())[0] is True
    assert (await comm_b.connect())[0] is True

    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        data["group_a"],
        {"type": "node_command", "command": {"type": "traceroute", "target": 1}},
    )
    assert await comm_a.receive_json_from() == {"type": "traceroute", "target": 1}

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(comm_b.receive_json_from(), timeout=0.5)

    await comm_a.disconnect()
    await comm_b.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mixed_mc_mt_rejected_without_disambiguator(
    create_managed_node, create_constellation, create_node_api_key
):
    from nodes.models import NodeAuth

    @database_sync_to_async
    def setup():
        constellation = create_constellation(protocol=Protocol.MESHTASTIC)
        mt_node = create_managed_node(
            protocol=Protocol.MESHTASTIC,
            constellation=constellation,
        )
        mc_node = create_managed_node(
            meshtastic_node_id=0,
            protocol=Protocol.MESHCORE,
            constellation=constellation,
            mc_pubkey=FEEDER_PUBKEY,
        )
        api_key = create_node_api_key(constellation=constellation)
        NodeAuth.objects.create(api_key=api_key, node=mt_node)
        NodeAuth.objects.create(api_key=api_key, node=mc_node)
        return api_key.key

    api_key = await setup()
    communicator = WebsocketCommunicator(application, f"/ws/nodes/?api_key={api_key}")
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mixed_mc_mt_with_disambiguators(create_managed_node, create_constellation, create_node_api_key):
    from channels.layers import get_channel_layer

    from nodes.models import NodeAuth

    @database_sync_to_async
    def setup():
        constellation = create_constellation(protocol=Protocol.MESHTASTIC)
        mt_node = create_managed_node(
            protocol=Protocol.MESHTASTIC,
            constellation=constellation,
        )
        mc_node = create_managed_node(
            meshtastic_node_id=0,
            protocol=Protocol.MESHCORE,
            constellation=constellation,
            mc_pubkey=FEEDER_PUBKEY,
        )
        api_key = create_node_api_key(constellation=constellation)
        NodeAuth.objects.create(api_key=api_key, node=mt_node)
        NodeAuth.objects.create(api_key=api_key, node=mc_node)
        return {
            "api_key": api_key.key,
            "mt_node_id": mt_node.meshtastic_node_id,
            "mt_group": managed_node_ws_group(mt_node),
            "mc_group": managed_node_ws_group(mc_node),
        }

    data = await setup()
    mt_comm = WebsocketCommunicator(
        application,
        f"/ws/nodes/?api_key={data['api_key']}&feeder_node_id={data['mt_node_id']}",
    )
    mc_comm = WebsocketCommunicator(
        application,
        f"/ws/nodes/?api_key={data['api_key']}&feeder_pubkey_prefix={FEEDER_PREFIX}",
    )
    assert (await mt_comm.connect())[0] is True
    assert (await mc_comm.connect())[0] is True

    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        data["mt_group"],
        {"type": "node_command", "command": {"type": "traceroute", "target": 99}},
    )
    assert await mt_comm.receive_json_from() == {"type": "traceroute", "target": 99}

    await channel_layer.group_send(
        data["mc_group"],
        {"type": "node_command", "command": {"type": "refresh_feeder_config"}},
    )
    assert await mc_comm.receive_json_from() == {"type": "refresh_feeder_config"}

    await mt_comm.disconnect()
    await mc_comm.disconnect()
