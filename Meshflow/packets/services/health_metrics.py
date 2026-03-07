"""Service for processing health metrics packets."""

from nodes.models import HealthMetrics, NodeLatestStatus
from packets.models import HealthMetricsPacket
from packets.services.base import BasePacketService


class HealthMetricsPacketService(BasePacketService):
    """Service for processing health metrics packets."""

    def _process_packet(self) -> None:
        """Process the health metrics packet and create a HealthMetrics record."""
        if not isinstance(self.packet, HealthMetricsPacket):
            raise ValueError("Packet must be a HealthMetricsPacket")

        reported_time = self.packet.reading_time or self.packet.first_reported_time

        HealthMetrics.objects.create(
            node=self.from_node,
            reported_time=reported_time,
            heart_bpm=self.packet.heart_bpm,
            spo2=self.packet.spo2,
            temperature=self.packet.temperature,
        )

        NodeLatestStatus.objects.update_or_create(
            node=self.from_node,
            defaults={
                "health_heart_bpm": self.packet.heart_bpm,
                "health_spo2": self.packet.spo2,
                "health_temperature": self.packet.temperature,
                "health_reported_time": reported_time,
            },
        )
