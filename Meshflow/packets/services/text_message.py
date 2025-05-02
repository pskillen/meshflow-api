"""Service for processing message packets."""

from text_messages.models import Message
from nodes.models import ObservedNode
from packets.models import MessagePacket
from packets.services.base import BasePacketService


class TextMessagePacketService(BasePacketService):
    """Service for processing message packets."""

    def process_packet(self) -> None:
        """Process the message packet and create a Message record."""
        if not isinstance(self.packet, MessagePacket):
            raise ValueError("Packet must be a MessagePacket")

        # Create a new Message record
        Message.objects.create(
            sender=ObservedNode.objects.get(node_id=self.packet.from_int),
            recipient_node_id=self.packet.to_int,
            message_text=self.packet.message_text,
            is_emoji=self.packet.emoji,
            reply_to_message_id=self.packet.reply_packet_id,
        )

        # Update the node's last_heard timestamp
        self._update_node_last_heard()
