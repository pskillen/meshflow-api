import logging
from django.dispatch import receiver

from nodes.models import ObservedNode
from packets.models import MessagePacket, PacketObservation
from packets.services.text_message import TextMessagePacketService

from .signals import message_packet_received

logger = logging.getLogger(__name__)


@receiver(message_packet_received)
def message_packet_received(sender, packet: MessagePacket, observer: ObservedNode, observation: PacketObservation, **kwargs):
    """Handle a message packet received signal."""
    logger.info(f"Message packet received: {packet.id}")

    service = TextMessagePacketService()
    service.process_packet(packet, observer, observation, user=None)
