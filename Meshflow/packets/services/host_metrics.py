"""Service for processing host metrics packets."""

from nodes.models import HostMetrics, NodeLatestStatus
from packets.models import HostMetricsPacket
from packets.services.base import BasePacketService


class HostMetricsPacketService(BasePacketService):
    """Service for processing host metrics packets."""

    def _process_packet(self) -> None:
        """Process the host metrics packet and create a HostMetrics record."""
        if not isinstance(self.packet, HostMetricsPacket):
            raise ValueError("Packet must be a HostMetricsPacket")

        reported_time = self.packet.reading_time or self.packet.first_reported_time

        HostMetrics.objects.create(
            node=self.from_node,
            reported_time=reported_time,
            uptime_seconds=self.packet.uptime_seconds,
            freemem_bytes=self.packet.freemem_bytes,
            diskfree1_bytes=self.packet.diskfree1_bytes,
            diskfree2_bytes=self.packet.diskfree2_bytes,
            diskfree3_bytes=self.packet.diskfree3_bytes,
            load1=self.packet.load1,
            load5=self.packet.load5,
            load15=self.packet.load15,
            user_string=self.packet.user_string,
        )

        NodeLatestStatus.objects.update_or_create(
            node=self.from_node,
            defaults={
                "host_uptime_seconds": self.packet.uptime_seconds,
                "host_freemem_bytes": self.packet.freemem_bytes,
                "host_reported_time": reported_time,
            },
        )
