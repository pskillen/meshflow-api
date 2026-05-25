"""Signal handlers for the ws app."""

from django.dispatch import receiver

from nodes.ws_notify import notify_node_claim_accepted
from packets.signals import node_claim_authorized, text_message_received

from .services.text_message import TextMessageWebSocketNotifier


@receiver(node_claim_authorized)
def send_node_claim_websocket_event(sender, node, claim, observer, **kwargs):
    """Push claim acceptance to the claiming user's WebSocket clients."""
    notify_node_claim_accepted(claim=claim, node=node)


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
