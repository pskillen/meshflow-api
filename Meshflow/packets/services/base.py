"""Base service for packet processing."""

from nodes.models import ObservedNode
from packets.models import RawPacket


class BasePacketService:
    """Base service for processing packets."""

    def __init__(self, packet: RawPacket, observer: ObservedNode):
        """Initialize the service with a packet and its observer."""
        self.packet = packet
        self.observer = observer

    def process_packet(self) -> None:
        """Process the packet and create any necessary related records."""
        raise NotImplementedError("Subclasses must implement process_packet")

    def _update_node_last_heard(self) -> None:
        """Update the last_heard timestamp of the node that sent the packet."""
        if self.packet.from_int and self.packet.first_reported_time:
            try:
                node = ObservedNode.objects.get(node_id=self.packet.from_int)
                node.last_heard = self.packet.first_reported_time
                node.save(update_fields=["last_heard"])
            except ObservedNode.DoesNotExist:
                # If the node doesn't exist, we don't need to update it
                pass
