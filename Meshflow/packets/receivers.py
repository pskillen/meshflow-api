import logging

from django.dispatch import receiver

from nodes.models import ObservedNode

from .models import DeviceMetricsPacket, MessagePacket, NodeInfoPacket, PacketObservation, PositionPacket
from .services.device_metrics import DeviceMetricsPacketService
from .services.node_info import NodeInfoPacketService
from .services.position import PositionPacketService
from .services.text_message import TextMessagePacketService
from .signals import (
    device_metrics_packet_received,
    message_packet_received,
    node_info_packet_received,
    position_packet_received,
)

logger = logging.getLogger(__name__)


@receiver(position_packet_received)
def position_packet_received(
    sender, packet: PositionPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a position packet received signal."""
    logger.info(f"Position packet received: {packet.id}")

    service = PositionPacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(device_metrics_packet_received)
def device_metrics_packet_received(
    sender, packet: DeviceMetricsPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a device metrics packet received signal."""
    logger.info(f"Device metrics packet received: {packet.id}")

    service = DeviceMetricsPacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(message_packet_received)
def message_packet_received(
    sender, packet: MessagePacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a message packet received signal."""
    logger.info(f"Message packet received: {packet.id}")

    service = TextMessagePacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(node_info_packet_received)
def node_info_packet_received(
    sender, packet: NodeInfoPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a node info packet received signal."""
    logger.info(f"Node info packet received: {packet.id}")

    service = NodeInfoPacketService()
    service.process_packet(packet, observer, observation, user=None)
