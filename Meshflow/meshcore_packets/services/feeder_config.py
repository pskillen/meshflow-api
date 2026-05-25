"""Push feeder bot config refresh to a connected MeshCore bot via WebSocket."""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync

from common.feeder_ws import (
    COMMAND_DISPATCH_UNAVAILABLE,
    FEEDER_BOT_NOT_CONNECTED,
    dispatch_node_command,
    feeder_ws_group_has_subscribers,
)
from common.protocol import Protocol
from common.ws_groups import managed_node_ws_group
from nodes.models import ManagedNode

logger = logging.getLogger(__name__)


def dispatch_feeder_config_refresh(managed_node: ManagedNode) -> str:
    """Dispatch refresh_feeder_config. Returns ``sent`` or an error code string."""
    if managed_node.protocol != Protocol.MESHCORE:
        return COMMAND_DISPATCH_UNAVAILABLE

    group = managed_node_ws_group(managed_node)

    async def _check_and_send() -> str:
        try:
            if not await feeder_ws_group_has_subscribers(group):
                logger.warning(
                    "Feeder config refresh: no WebSocket subscriber on group %s",
                    group,
                )
                return FEEDER_BOT_NOT_CONNECTED
        except Exception as exc:
            logger.exception("Feeder config refresh: presence check failed: %s", exc)
            return COMMAND_DISPATCH_UNAVAILABLE

        try:
            await dispatch_node_command(
                group,
                {"type": "refresh_feeder_config"},
            )
        except Exception as exc:
            logger.exception("Feeder config refresh: group_send failed: %s", exc)
            return COMMAND_DISPATCH_UNAVAILABLE
        return "sent"

    return async_to_sync(_check_and_send)()
