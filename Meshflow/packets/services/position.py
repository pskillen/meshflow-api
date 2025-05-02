"""Service for processing position packets."""

from nodes.models import LocationSource, Position
from packets.models import PositionPacket
from packets.services.base import BasePacketService


class PositionPacketService(BasePacketService):
    """Service for processing position packets."""

    def _process_packet(self) -> None:
        """Process the position packet and create a Position record."""
        if not isinstance(self.packet, PositionPacket):
            raise ValueError("Packet must be a PositionPacket")

        # Create a new Position record
        Position.objects.create(
            node=self.from_node,
            reported_time=self.packet.position_time or self.packet.first_reported_time,
            latitude=self.packet.latitude,
            longitude=self.packet.longitude,
            altitude=self.packet.altitude,
            heading=self.packet.heading,
            location_source=self.packet.location_source or LocationSource.UNSET,
            precision_bits=self.packet.precision_bits,
            ground_speed=self.packet.ground_speed,
            ground_track=self.packet.ground_track,
        )

