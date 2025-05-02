"""Factory for creating packet services."""

from packets.models import DeviceMetricsPacket, MessagePacket, NodeInfoPacket, PositionPacket, RawPacket
from packets.services.base import BasePacketService
from packets.services.device_metrics import DeviceMetricsPacketService
from packets.services.node_info import NodeInfoPacketService
from packets.services.position import PositionPacketService
from packets.services.text_message import TextMessagePacketService


class PacketServiceFactory:
    """Factory for creating packet services."""

    @staticmethod
    def create_service(packet: RawPacket) -> "BasePacketService":
        """Create the appropriate service for the given packet type."""
        if isinstance(packet, PositionPacket):
            return PositionPacketService()
        elif isinstance(packet, DeviceMetricsPacket):
            return DeviceMetricsPacketService()
        elif isinstance(packet, MessagePacket):
            return TextMessagePacketService()
        elif isinstance(packet, NodeInfoPacket):
            return NodeInfoPacketService()
        else:
            # For packet types that don't need additional processing
            return None
