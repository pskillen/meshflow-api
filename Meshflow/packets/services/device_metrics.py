"""Service for processing device metrics packets."""

from nodes.models import DeviceMetrics, NodeLatestStatus
from packets.models import DeviceMetricsPacket
from packets.services.base import BasePacketService
from packets.signals import device_metrics_recorded


class DeviceMetricsPacketService(BasePacketService):
    """Service for processing device metrics packets."""

    def _process_packet(self) -> None:
        """Process the device metrics packet and create a DeviceMetrics record."""
        if not isinstance(self.packet, DeviceMetricsPacket):
            raise ValueError("Packet must be a DeviceMetricsPacket")

        reported_time = self.packet.reading_time or self.packet.first_reported_time

        # Create a new DeviceMetrics record
        battery_level = float(self.packet.battery_level) if self.packet.battery_level is not None else None
        dm = DeviceMetrics.objects.create(
            node=self.from_node,
            reported_time=reported_time,
            battery_level=battery_level,
            voltage=self.packet.voltage,
            meshtastic_channel_utilization=self.packet.meshtastic_channel_utilization,
            meshtastic_air_util_tx=self.packet.meshtastic_air_util_tx,
            uptime_seconds=self.packet.uptime_seconds,
        )

        # Update NodeLatestStatus with latest device metrics (preserves position)
        NodeLatestStatus.objects.update_or_create(
            node=self.from_node,
            defaults={
                "battery_level": self.packet.battery_level,
                "voltage": self.packet.voltage,
                "meshtastic_channel_utilization": self.packet.meshtastic_channel_utilization,
                "meshtastic_air_util_tx": self.packet.meshtastic_air_util_tx,
                "uptime_seconds": self.packet.uptime_seconds,
                "metrics_reported_time": reported_time,
            },
        )
        self._update_inferred_max_hops("TELEMETRY_APP")

        device_metrics_recorded.send(
            sender=self.__class__,
            observed_node=self.from_node,
            device_metrics=dm,
            battery_level=battery_level,
            reported_time=reported_time,
        )
