"""Broadcast traceroute status changes to WebSocket clients via Redis channel layer."""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def notify_traceroute_status_changed(tr_id: int, status: str) -> None:
    """
    Broadcast to all connected traceroute WebSocket clients that a traceroute's status changed.
    Uses Redis channel layer for horizontal scaling.
    """
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "traceroutes",
            {"type": "traceroute_update", "id": tr_id, "status": status},
        )
        logger.debug("Broadcast traceroute_update id=%s status=%s", tr_id, status)
    except Exception as e:
        logger.warning("Failed to broadcast traceroute_update: %s", e)
