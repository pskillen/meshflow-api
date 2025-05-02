"""Service for processing message packets."""

from text_messages.models import TextMessage
from packets.models import MessagePacket
from packets.services.base import BasePacketService


class TextMessagePacketService(BasePacketService):
    """Service for processing message packets."""

    def _process_packet(self) -> None:
        """Process the message packet and create a Message record."""
        if not isinstance(self.packet, MessagePacket):
            raise ValueError("Packet must be a MessagePacket")
        
        # the channel is based on the observer's channel mapping
        channel_idx = self.observation.channel
        channel = self.observer.get_channel(channel_idx)

        # Create a new Message record
        TextMessage.objects.create(
            sender=self.from_node,
            recipient_node_id=self.packet.to_int,
            message_text=self.packet.message_text,
            is_emoji=self.packet.emoji,
            reply_to_message_id=self.packet.reply_packet_id,
            channel=channel,
        )
