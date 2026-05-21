"""Helpers for managed-node feeder bot WebSocket presence and command dispatch."""

from __future__ import annotations

import logging

from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

FEEDER_BOT_NOT_CONNECTED = "feeder_bot_not_connected"
COMMAND_DISPATCH_UNAVAILABLE = "command_dispatch_unavailable"


async def feeder_ws_group_has_subscribers(group: str) -> bool:
    """Return True if at least one bot WebSocket is subscribed to ``group``."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return False
    if not hasattr(channel_layer, "group_channels"):
        logger.warning("Channel layer does not support group_channels; assuming feeder offline")
        return False
    channels = await channel_layer.group_channels(group)
    return bool(channels)


async def dispatch_node_command(group: str, command: dict) -> None:
    """Send a command to feeder bots on ``group``; raises on Redis/channel errors."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        raise RuntimeError("Channel layer is not configured")
    await channel_layer.group_send(
        group,
        {
            "type": "node_command",
            "command": command,
        },
    )
