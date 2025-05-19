import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from text_messages.models import TextMessage

from ..serializers import TextMessageWSSerializer

logger = logging.getLogger(__name__)


class TextMessageWebSocketNotifier:

    def notify(self, message: TextMessage):
        try:
            # Serialize the message
            serializer = TextMessageWSSerializer(message)
            message_data = serializer.data

            # Get the channel layer
            channel_layer = get_channel_layer()

            logger.warning(f"Sending message to WS: {message_data}")

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
