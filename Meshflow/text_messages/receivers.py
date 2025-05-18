"""Signal handlers for text messages."""

import logging

from django.dispatch import receiver

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from packets.signals import text_message_received
from text_messages.serializers import TextMessageSerializer

logger = logging.getLogger(__name__)


@receiver(text_message_received)
def send_text_message_websocket_event(sender, message, observer, **kwargs):
    """
    Handle a message packet by creating a TextMessage and sending a WebSocket event.

    Args:
        sender: The sender of the signal
        message: The TextMessage object
        observer: The ManagedNode that observed the message
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
