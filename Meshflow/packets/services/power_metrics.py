"""Service for processing power metrics packets."""

from nodes.models import PowerMetrics
from packets.models import PowerMetricsPacket
from packets.services.base import BasePacketService


class PowerMetricsPacketService(BasePacketService):
    """Service for processing power metrics packets. Stores only; no NodeLatestStatus update."""

    def _process_packet(self) -> None:
        """Process the power metrics packet and create a PowerMetrics record."""
        if not isinstance(self.packet, PowerMetricsPacket):
            raise ValueError("Packet must be a PowerMetricsPacket")

        reported_time = self.packet.reading_time or self.packet.first_reported_time

        PowerMetrics.objects.create(
            node=self.from_node,
            reported_time=reported_time,
            ch1_voltage=self.packet.ch1_voltage,
            ch1_current=self.packet.ch1_current,
            ch2_voltage=self.packet.ch2_voltage,
            ch2_current=self.packet.ch2_current,
            ch3_voltage=self.packet.ch3_voltage,
            ch3_current=self.packet.ch3_current,
            ch4_voltage=self.packet.ch4_voltage,
            ch4_current=self.packet.ch4_current,
            ch5_voltage=self.packet.ch5_voltage,
            ch5_current=self.packet.ch5_current,
            ch6_voltage=self.packet.ch6_voltage,
            ch6_current=self.packet.ch6_current,
            ch7_voltage=self.packet.ch7_voltage,
            ch7_current=self.packet.ch7_current,
            ch8_voltage=self.packet.ch8_voltage,
            ch8_current=self.packet.ch8_current,
        )
