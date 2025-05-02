"""Factory for creating packet services."""

from packets.models import DeviceMetricsPacket, MessagePacket, PositionPacket, RawPacket
from packets.services.base import BasePacketService
from packets.services.device_metrics import DeviceMetricsPacketService
from packets.services.text_message import TextMessagePacketService
from packets.services.position import PositionPacketService


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
        else:
            # For packet types that don't need additional processing
            return None
