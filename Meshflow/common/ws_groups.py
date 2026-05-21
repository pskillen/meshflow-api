"""Channel layer group names for managed-node bot WebSockets."""

from common.protocol import Protocol
from nodes.models import ManagedNode


def managed_node_ws_group(managed_node: ManagedNode) -> str:
    """Group name for pushing commands to a connected feeder bot."""
    if managed_node.protocol == Protocol.MESHCORE:
        return f"node_mc_{managed_node.internal_id}"
    return f"node_{managed_node.meshtastic_node_id}"
