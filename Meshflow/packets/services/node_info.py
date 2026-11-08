from common.meshtastic_enums import normalise_hw_model
from common.meshtastic_identity import identity_fields, protect_identity
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

        # A NodeInfo packet's ``node_id`` is the sender's own id, so there is no "packet is about another node"
        # check to make here (the old int-vs-str guard never matched and would have skipped every update).
        # Blank/zero MACs, blank keys and 24-byte-truncated names must not clobber stored identity data.
        updates = protect_identity(
            sender,
            {
                "short_name": self.packet.short_name,
                "long_name": self.packet.long_name,
                "mac_addr": self.packet.mac_address,
                "meshtastic_public_key": self.packet.public_key,
            },
        )

        # update the ObservedNode
        for field, value in updates.items():
            setattr(sender, field, value)
        sender.meshtastic_hw_model = normalise_hw_model(self.packet.hw_model)
        sender.meshtastic_role = self.packet.role
        if "meshtastic_public_key" in updates:
            for field, value in identity_fields(updates["meshtastic_public_key"]).items():
                setattr(sender, field, value)
        sender.meshtastic_is_licensed = self.packet.is_licensed
        sender.meshtastic_is_unmessagable = self.packet.is_unmessagable
        sender.save()
