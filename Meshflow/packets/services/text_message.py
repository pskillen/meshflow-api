"""Service for processing message packets."""

import logging

from common.mesh_node_helpers import MESHTASTIC_BROADCAST_ID
from common.protocol import Protocol
from nodes.claim_authorization import try_accept_node_claim
from packets.models import MessagePacket
from packets.services.base import BasePacketService
from packets.signals import text_message_received
from text_messages.models import TextMessage

logger = logging.getLogger(__name__)


class TextMessagePacketService(BasePacketService):
    """Service for processing message packets."""

    def _process_packet(self) -> None:
        """Process the message packet and create a Message record."""
        if not isinstance(self.packet, MessagePacket):
            raise ValueError("Packet must be a MessagePacket")

        # ensure the message hasn't already been processed
        if TextMessage.objects.filter(original_packet=self.packet).exists():
            return

        self._create_message()
        self._authorize_node_claim()

    def _create_message(self) -> None:
        """Create a new TextMessage record."""

        # Create a new Message record
        message = TextMessage.objects.create(
            protocol=Protocol.MESHTASTIC,
            sender=self.from_node,
            original_packet=self.packet,
            recipient_meshtastic_node_id=self.packet.to_int,
            message_text=self.packet.message_text,
            is_emoji=self.packet.emoji,
            reply_to_meshtastic_packet_id=self.packet.reply_packet_id,
            sent_at=getattr(self.observation, "rx_time", None) or self.packet.first_reported_time,
            channel=self.observation.channel,
        )

        if self.packet.to_int == MESHTASTIC_BROADCAST_ID:
            # send the text message packet received signal
            text_message_received.send(sender=self, message=message, observer=self.observer)

    def _authorize_node_claim(self) -> None:
        """Authorize a user's claim to a node via the claim key in the message."""
        if self.packet.to_int == MESHTASTIC_BROADCAST_ID:
            return

        try_accept_node_claim(
            sender=self.from_node,
            message_text=self.packet.message_text,
            observer=self.observer,
            sender_service=self,
        )
