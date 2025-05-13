from packets.models import NodeInfoPacket
from packets.services.base import BasePacketService


class NodeInfoPacketService(BasePacketService):
    """Service for processing node info packets."""

    packet: NodeInfoPacket

    def _process_packet(self) -> None:
        """Process the node info packet and update the ObservedNode if required."""
        if not isinstance(self.packet, NodeInfoPacket):
            raise ValueError("Packet must be a NodeInfoPacket")
        sender = self.from_node

        # check if the node info packet is for the current node
        if sender.node_id == self.packet.node_id:
            return

        # update the ObservedNode
        sender.short_name = self.packet.short_name
        sender.long_name = self.packet.long_name
        sender.hw_model = self.packet.hw_model
        sender.sw_version = self.packet.sw_version
        sender.role = self.packet.role

        # we don't store public keys yet
        # I don't see a use case for updating the MAC address
        sender.save()
