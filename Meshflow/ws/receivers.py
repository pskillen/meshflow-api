"""Signal handlers for the ws app."""

from django.dispatch import receiver

from packets.signals import text_message_received

from .services.text_message import TextMessageWebSocketNotifier


@receiver(text_message_received)
def send_text_message_websocket_event(sender, message, observer, **kwargs):
    """
    Handle a message packet by creating a TextMessage and sending a WebSocket event.

    Args:
        sender: The sender of the signal
        message: The TextMessage object
        observer: The ManagedNode that observed the message
    """
    notifier = TextMessageWebSocketNotifier()
    notifier.notify(message)
