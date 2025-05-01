"""Service for processing device metrics packets."""

from nodes.models import DeviceMetrics, ObservedNode
from packets.models import DeviceMetricsPacket
from packets.services.base import BasePacketService


class DeviceMetricsPacketService(BasePacketService):
    """Service for processing device metrics packets."""

    def process_packet(self) -> None:
        """Process the device metrics packet and create a DeviceMetrics record."""
        if not isinstance(self.packet, DeviceMetricsPacket):
            raise ValueError("Packet must be a DeviceMetricsPacket")

        # Create a new DeviceMetrics record
        DeviceMetrics.objects.create(
            node=ObservedNode.objects.get(node_id=self.packet.from_int),
            reported_time=self.packet.reading_time or self.packet.first_reported_time,
            battery_level=self.packet.battery_level or 0.0,
            voltage=self.packet.voltage or 0.0,
            channel_utilization=self.packet.channel_utilization or 0.0,
            air_util_tx=self.packet.air_util_tx or 0.0,
            uptime_seconds=self.packet.uptime_seconds or 0,
        )

        # Update the node's last_heard timestamp
        self._update_node_last_heard()
