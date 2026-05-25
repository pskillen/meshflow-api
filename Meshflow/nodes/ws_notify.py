"""Push node-claim acceptance events to the claiming user's WebSocket clients."""

import logging

from django.utils import timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from common.ws_groups import user_claims_ws_group
from nodes.models import NodeOwnerClaim, ObservedNode

logger = logging.getLogger(__name__)


def notify_node_claim_accepted(*, claim: NodeOwnerClaim, node: ObservedNode) -> None:
    """Notify the claiming user that their ownership proof was accepted."""
    try:
        channel_layer = get_channel_layer()
        accepted_at = claim.accepted_at or timezone.now()
        payload = {
            "event": "node_claim_accepted",
            "node_internal_id": str(node.internal_id),
            "node_id_str": node.node_id_str,
            "protocol": node.protocol,
            "accepted_at": accepted_at.isoformat(),
        }
        async_to_sync(channel_layer.group_send)(
            user_claims_ws_group(claim.user_id),
            {"type": "node_claim_update", "payload": payload},
        )
        logger.debug(
            "Sent node_claim_accepted to user_id=%s node=%s",
            claim.user_id,
            node.node_id_str,
        )
    except Exception as e:
        logger.warning("Failed to send node_claim_accepted WebSocket: %s", e)
