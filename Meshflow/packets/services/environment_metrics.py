"""Service for processing environment metrics packets."""

from nodes.models import EnvironmentMetrics, NodeLatestStatus
from packets.models import EnvironmentMetricsPacket
from packets.services.base import BasePacketService


class EnvironmentMetricsPacketService(BasePacketService):
    """Service for processing environment metrics packets."""

    def _process_packet(self) -> None:
        """Process the environment metrics packet and create an EnvironmentMetrics record."""
        if not isinstance(self.packet, EnvironmentMetricsPacket):
            raise ValueError("Packet must be an EnvironmentMetricsPacket")

        reported_time = self.packet.reading_time or self.packet.first_reported_time

        EnvironmentMetrics.objects.create(
            node=self.from_node,
            reported_time=reported_time,
            temperature=self.packet.temperature,
            relative_humidity=self.packet.relative_humidity,
            barometric_pressure=self.packet.barometric_pressure,
            gas_resistance=self.packet.gas_resistance,
            iaq=self.packet.iaq,
            voltage=self.packet.voltage,
            current=self.packet.current,
            distance=self.packet.distance,
            lux=self.packet.lux,
            white_lux=self.packet.white_lux,
            ir_lux=self.packet.ir_lux,
            uv_lux=self.packet.uv_lux,
            wind_direction=self.packet.wind_direction,
            wind_speed=self.packet.wind_speed,
            weight=self.packet.weight,
            wind_gust=self.packet.wind_gust,
            wind_lull=self.packet.wind_lull,
            radiation=self.packet.radiation,
            rainfall_1h=self.packet.rainfall_1h,
            rainfall_24h=self.packet.rainfall_24h,
            soil_moisture=self.packet.soil_moisture,
            soil_temperature=self.packet.soil_temperature,
        )

        NodeLatestStatus.objects.update_or_create(
            node=self.from_node,
            defaults={
                "environment_temperature": self.packet.temperature,
                "environment_relative_humidity": self.packet.relative_humidity,
                "environment_barometric_pressure": self.packet.barometric_pressure,
                "environment_reported_time": reported_time,
            },
        )
