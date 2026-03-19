"""Service for processing air quality metrics packets."""

from nodes.models import AirQualityMetrics, NodeLatestStatus
from packets.models import AirQualityMetricsPacket
from packets.services.base import BasePacketService


class AirQualityMetricsPacketService(BasePacketService):
    """Service for processing air quality metrics packets."""

    def _process_packet(self) -> None:
        """Process the air quality metrics packet and create an AirQualityMetrics record."""
        if not isinstance(self.packet, AirQualityMetricsPacket):
            raise ValueError("Packet must be an AirQualityMetricsPacket")

        reported_time = self.packet.reading_time or self.packet.first_reported_time

        AirQualityMetrics.objects.create(
            node=self.from_node,
            reported_time=reported_time,
            pm10_standard=self.packet.pm10_standard,
            pm25_standard=self.packet.pm25_standard,
            pm100_standard=self.packet.pm100_standard,
            pm10_environmental=self.packet.pm10_environmental,
            pm25_environmental=self.packet.pm25_environmental,
            pm100_environmental=self.packet.pm100_environmental,
            particles_03um=self.packet.particles_03um,
            particles_05um=self.packet.particles_05um,
            particles_10um=self.packet.particles_10um,
            particles_25um=self.packet.particles_25um,
            particles_50um=self.packet.particles_50um,
            particles_100um=self.packet.particles_100um,
            co2=self.packet.co2,
            co2_temperature=self.packet.co2_temperature,
            co2_humidity=self.packet.co2_humidity,
            form_formaldehyde=self.packet.form_formaldehyde,
            form_humidity=self.packet.form_humidity,
            form_temperature=self.packet.form_temperature,
            pm40_standard=self.packet.pm40_standard,
            particles_40um=self.packet.particles_40um,
            pm_temperature=self.packet.pm_temperature,
            pm_humidity=self.packet.pm_humidity,
            pm_voc_idx=self.packet.pm_voc_idx,
            pm_nox_idx=self.packet.pm_nox_idx,
            particles_tps=self.packet.particles_tps,
        )

        NodeLatestStatus.objects.update_or_create(
            node=self.from_node,
            defaults={
                "air_quality_pm25_standard": self.packet.pm25_standard,
                "air_quality_co2": self.packet.co2,
                "air_quality_reported_time": reported_time,
                "inferred_max_hops": self.observation.hop_start,
            },
        )
