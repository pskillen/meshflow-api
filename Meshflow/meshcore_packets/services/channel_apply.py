"""Push MeshCore channel config to a connected feeder bot via WebSocket."""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync

from common.feeder_ws import (
    COMMAND_DISPATCH_UNAVAILABLE,
    FEEDER_BOT_NOT_CONNECTED,
    dispatch_node_command,
    feeder_ws_group_has_subscribers,
)
from common.mc_channel_labels import managed_node_mc_channels_queryset, message_channel_to_apply_entry
from common.protocol import Protocol
from common.ws_groups import managed_node_ws_group
from nodes.models import ManagedNode

logger = logging.getLogger(__name__)


def build_apply_channels_for_managed_node(managed_node: ManagedNode) -> list[dict]:
    """Snapshot entries for apply_mc_channel_config from the feeder mirror."""
    if managed_node.protocol != Protocol.MESHCORE:
        return []
    return [message_channel_to_apply_entry(ch) for ch in managed_node_mc_channels_queryset(managed_node)]


def dispatch_mc_channel_apply(managed_node: ManagedNode, channels: list[dict]) -> str:
    """Dispatch apply_mc_channel_config. Returns ``sent`` or an error code string."""
    group = managed_node_ws_group(managed_node)

    async def _check_and_send() -> str:
        try:
            if not await feeder_ws_group_has_subscribers(group):
                logger.warning(
                    "MC channel apply: no WebSocket subscriber on group %s",
                    group,
                )
                return FEEDER_BOT_NOT_CONNECTED
        except Exception as exc:
            logger.exception("MC channel apply: feeder presence check failed: %s", exc)
            return COMMAND_DISPATCH_UNAVAILABLE

        try:
            await dispatch_node_command(
                group,
                {
                    "type": "apply_mc_channel_config",
                    "channels": channels,
                },
            )
        except Exception as exc:
            logger.exception("MC channel apply: group_send failed: %s", exc)
            return COMMAND_DISPATCH_UNAVAILABLE
        return "sent"

    return async_to_sync(_check_and_send)()


def apply_mc_channels_to_feeder(managed_node: ManagedNode, channels: list[dict] | None = None) -> str:
    """Push channel config to the feeder bot. Uses mirror when *channels* is omitted."""
    if managed_node.protocol != Protocol.MESHCORE:
        raise ValueError("apply_mc_channels_to_feeder requires a MeshCore managed node")
    payload = channels if channels is not None else build_apply_channels_for_managed_node(managed_node)
    return dispatch_mc_channel_apply(managed_node, payload)
