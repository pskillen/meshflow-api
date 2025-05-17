"""Service for processing message packets."""

import logging
import re

from django.utils import timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from common.mesh_node_helpers import BROADCAST_ID
from nodes.models import NodeOwnerClaim
from packets.models import MessagePacket
from packets.services.base import BasePacketService
from text_messages.models import TextMessage
from text_messages.serializers import TextMessageSerializer

logger = logging.getLogger(__name__)


class TextMessagePacketService(BasePacketService):
    """Service for processing message packets."""

    # regex for a claim key (2-3 words and 2-3 digits)
    _CLAIM_KEY_REGEX = r"^\s*(\w+\s+){2,3}\d{2,3}\s*$"

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
        """Create a new TextMessage record and send a WebSocket event."""

        # Create a new Message record
        message = TextMessage.objects.create(
            sender=self.from_node,
            original_packet=self.packet,
            recipient_node_id=self.packet.to_int,
            message_text=self.packet.message_text,
            is_emoji=self.packet.emoji,
            reply_to_message_id=self.packet.reply_packet_id,
            # the channel is based on the observer's channel mapping
            channel=self.observation.channel,
        )

        # Send a WebSocket event with the new message
        self._send_message_event(message)

    def _send_message_event(self, message: TextMessage) -> None:
        """
        Send a WebSocket event with the new message.

        Args:
            message: The TextMessage object to send
        """
        try:
            # Serialize the message
            serializer = TextMessageSerializer(message)
            message_data = serializer.data

            # Get the channel layer
            channel_layer = get_channel_layer()

            # Send the message to the text_messages group
            async_to_sync(channel_layer.group_send)(
                "text_messages",
                {
                    "type": "text_message",
                    "message": message_data,
                },
            )

            logger.info(f"Sent WebSocket event for message {message.id}")
        except Exception as e:
            # Log the error but don't raise it to avoid breaking the message processing
            logger.error(f"Error sending WebSocket event: {e}")

    def _authorize_node_claim(self) -> None:
        """Authorize a user's claim to a node via the claim key in the message."""

        # Only accept claims via direct messages
        if self.packet.to_int == BROADCAST_ID:
            return

        # check whether this looks like a claim key (2-3 words and 2-3 digits)
        # reduces unnecessary database queries
        if not re.match(self._CLAIM_KEY_REGEX, self.packet.message_text):
            return

        # remove whitespace from the claim key
        claim_key = " ".join(self.packet.message_text.strip().split()).lower()
        logger.info(f"Checking node claim for {self.from_node.node_id_str}: {claim_key}")

        # check if this key matches a claim
        claim = NodeOwnerClaim.objects.filter(
            node=self.from_node,
            claim_key=claim_key,
            accepted_at__isnull=True,
        ).first()
        if claim is None:
            return

        logger.info(f"Authorizing node claim for {self.from_node.node_id_str} by {claim.user.username}")

        # update the node's owner
        self.from_node.claimed_by = claim.user
        self.from_node.save(update_fields=["claimed_by"])

        # delete the claim
        claim.accepted_at = timezone.now()
        claim.save(update_fields=["accepted_at"])
