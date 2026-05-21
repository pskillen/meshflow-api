"""Helpers for managed-node feeder bot WebSocket presence and command dispatch."""

from __future__ import annotations

import logging
import time

from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

FEEDER_BOT_NOT_CONNECTED = "feeder_bot_not_connected"
COMMAND_DISPATCH_UNAVAILABLE = "command_dispatch_unavailable"


def _ws_json_safe(value):
    """Recursively coerce channel-layer payloads to msgpack-safe plain Python."""
    from django.utils.functional import Promise

    if isinstance(value, Promise):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _ws_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_ws_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


async def _redis_group_has_channels(layer, group: str) -> bool:
    """Presence check for channels_redis (group is a ZSET at asgi:group:{name})."""
    key = layer._group_key(group)
    connection = layer.connection(layer.consistent_hash(group))
    await connection.zremrangebyscore(
        key,
        min=0,
        max=int(time.time()) - layer.group_expiry,
    )
    names = await connection.zrange(key, 0, -1)
    return bool(names)


async def _inmemory_group_has_channels(layer, group: str) -> bool:
    """Presence check for InMemoryChannelLayer (tests)."""
    members = layer.groups.get(group) or {}
    now = time.time()
    return any(now - ts < layer.group_expiry for ts in members.values())


async def feeder_ws_group_has_subscribers(group: str) -> bool:
    """Return True if at least one bot WebSocket is subscribed to ``group``."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return False

    try:
        from channels.layers import InMemoryChannelLayer
        from channels_redis.core import RedisChannelLayer
    except ImportError:
        RedisChannelLayer = None  # type: ignore[misc, assignment]
        InMemoryChannelLayer = None  # type: ignore[misc, assignment]

    if RedisChannelLayer is not None and isinstance(channel_layer, RedisChannelLayer):
        return await _redis_group_has_channels(channel_layer, group)

    if InMemoryChannelLayer is not None and isinstance(channel_layer, InMemoryChannelLayer):
        return await _inmemory_group_has_channels(channel_layer, group)

    logger.warning(
        "Channel layer %s has no membership probe; assuming feeder offline",
        type(channel_layer).__name__,
    )
    return False


async def dispatch_node_command(group: str, command: dict) -> None:
    """Send a command to feeder bots on ``group``; raises on Redis/channel errors."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        raise RuntimeError("Channel layer is not configured")
    await channel_layer.group_send(
        group,
        _ws_json_safe(
            {
                "type": "node_command",
                "command": command,
            }
        ),
    )
