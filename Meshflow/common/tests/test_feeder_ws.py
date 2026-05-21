"""Tests for feeder WebSocket presence helpers."""

import time
from unittest.mock import AsyncMock, MagicMock

from django.utils.translation import gettext_lazy

import msgpack
import pytest

from common.feeder_ws import _ws_json_safe, dispatch_node_command, feeder_ws_group_has_subscribers


@pytest.mark.asyncio
async def test_redis_group_has_subscribers_when_zset_non_empty(monkeypatch):
    from channels_redis.core import RedisChannelLayer

    layer = MagicMock(spec=RedisChannelLayer)
    layer._group_key.return_value = "asgi:group:node_mc_test"
    layer.consistent_hash.return_value = 0
    layer.group_expiry = 86400
    connection = AsyncMock()
    connection.zrange.return_value = [b"specific.channel.name"]
    layer.connection.return_value = connection

    monkeypatch.setattr(
        "common.feeder_ws.get_channel_layer",
        lambda: layer,
    )

    assert await feeder_ws_group_has_subscribers("node_mc_test") is True
    connection.zremrangebyscore.assert_awaited_once()
    connection.zrange.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_group_has_no_subscribers_when_zset_empty(monkeypatch):
    from channels_redis.core import RedisChannelLayer

    layer = MagicMock(spec=RedisChannelLayer)
    layer._group_key.return_value = "asgi:group:node_mc_empty"
    layer.consistent_hash.return_value = 0
    layer.group_expiry = 86400
    connection = AsyncMock()
    connection.zrange.return_value = []
    layer.connection.return_value = connection

    monkeypatch.setattr(
        "common.feeder_ws.get_channel_layer",
        lambda: layer,
    )

    assert await feeder_ws_group_has_subscribers("node_mc_empty") is False


@pytest.mark.asyncio
async def test_inmemory_group_has_subscribers(monkeypatch):
    from channels.layers import InMemoryChannelLayer

    layer = InMemoryChannelLayer()
    layer.groups["node_mc_mem"] = {"test.channel": time.time()}

    monkeypatch.setattr(
        "common.feeder_ws.get_channel_layer",
        lambda: layer,
    )

    assert await feeder_ws_group_has_subscribers("node_mc_mem") is True


def test_ws_json_safe_coerces_lazy_translation_proxy():
    payload = {
        "type": "node_command",
        "command": {
            "type": "apply_mc_channels",
            "channels": [
                {
                    "mc_channel_type": gettext_lazy("HASHTAG"),
                    "name": "test",
                }
            ],
        },
    }
    safe = _ws_json_safe(payload)
    msgpack.packb(safe)
    assert safe["command"]["channels"][0]["mc_channel_type"] == "HASHTAG"


@pytest.mark.asyncio
async def test_dispatch_node_command_sends_msgpack_safe_payload(monkeypatch):
    layer = AsyncMock()
    monkeypatch.setattr("common.feeder_ws.get_channel_layer", lambda: layer)

    command = {
        "type": "apply_mc_channels",
        "channels": [{"mc_channel_type": gettext_lazy("PUBLIC"), "name": "x"}],
    }
    await dispatch_node_command("node_mc_test", command)

    layer.group_send.assert_awaited_once()
    message = layer.group_send.await_args[0][1]
    msgpack.packb(message)
    assert message["command"]["channels"][0]["mc_channel_type"] == "PUBLIC"
