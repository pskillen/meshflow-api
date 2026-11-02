"""Channel layer group names for managed-node bot WebSockets."""

from common.protocol import Protocol
from nodes.models import ManagedNode


def managed_node_ws_group(managed_node: ManagedNode) -> str:
    """Group name for pushing commands to a connected feeder bot.

    Keyed on the ManagedNode primary key (``internal_id``), never a protocol node number, so
    the group survives a Meshtastic node-number change (2.8 re-key). Senders and the
    ``NodeConsumer`` must both go through this helper.
    """
    prefix = "node_mc" if managed_node.protocol == Protocol.MESHCORE else "node_mt"
    return f"{prefix}_{managed_node.internal_id}"


def user_claims_ws_group(user_id: int) -> str:
    """Group name for pushing node-claim acceptance events to a logged-in user."""
    return f"user_claims_{user_id}"
