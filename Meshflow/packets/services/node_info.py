from common.meshtastic_enums import normalise_hw_model
from common.meshtastic_identity import identity_fields, protect_identity
from nodes.services.identity_links import detect_after_nodeinfo
from nodes.services.node_firmware import refresh_inferred_firmware, refresh_row_numbered_by_key
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

        # What is stored now, to tell a real change from a repeat of the same NodeInfo (repeats cost no identity work).
        stored_key = sender.meshtastic_public_key
        stored_mac = sender.mac_addr

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
        refresh_inferred_firmware(sender)
        sender.save()
        key_written = "meshtastic_public_key" in updates
        if key_written:
            refresh_row_numbered_by_key(sender)
        # Identity links: key evidence, then MAC evidence (on-air only: NodeDB uploads zero other nodes' MACs).
        # Only a key or MAC that differs from what was stored can change the answer.
        key_changed = key_written and updates["meshtastic_public_key"] != stored_key
        mac_changed = "mac_addr" in updates and updates["mac_addr"] != stored_mac
        if key_changed or mac_changed:
            detect_after_nodeinfo(sender, self.packet.mac_address if mac_changed else None, key_written=key_changed)
