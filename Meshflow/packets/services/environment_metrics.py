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
            adc_voltage_ch0=self.packet.adc_voltage_ch0,
            adc_voltage_ch1=self.packet.adc_voltage_ch1,
            adc_voltage_ch2=self.packet.adc_voltage_ch2,
            adc_voltage_ch3=self.packet.adc_voltage_ch3,
            adc_voltage_ch4=self.packet.adc_voltage_ch4,
            adc_voltage_ch5=self.packet.adc_voltage_ch5,
            adc_voltage_ch6=self.packet.adc_voltage_ch6,
            adc_voltage_ch7=self.packet.adc_voltage_ch7,
            one_wire_temperature_ch0=self.packet.one_wire_temperature_ch0,
            one_wire_temperature_ch1=self.packet.one_wire_temperature_ch1,
            one_wire_temperature_ch2=self.packet.one_wire_temperature_ch2,
            one_wire_temperature_ch3=self.packet.one_wire_temperature_ch3,
            one_wire_temperature_ch4=self.packet.one_wire_temperature_ch4,
            one_wire_temperature_ch5=self.packet.one_wire_temperature_ch5,
            one_wire_temperature_ch6=self.packet.one_wire_temperature_ch6,
            one_wire_temperature_ch7=self.packet.one_wire_temperature_ch7,
            lightning_strike_count_1h=self.packet.lightning_strike_count_1h,
            lightning_distance_km=self.packet.lightning_distance_km,
        )

        NodeLatestStatus.objects.update_or_create(
            node=self.from_node,
            defaults={
                "environment_temperature": self.packet.temperature,
                "environment_relative_humidity": self.packet.relative_humidity,
                "environment_barometric_pressure": self.packet.barometric_pressure,
                "environment_gas_resistance": self.packet.gas_resistance,
                "environment_iaq": self.packet.iaq,
                "environment_lux": self.packet.lux,
                "environment_wind_direction": self.packet.wind_direction,
                "environment_wind_speed": self.packet.wind_speed,
                "environment_radiation": self.packet.radiation,
                "environment_rainfall_1h": self.packet.rainfall_1h,
                "environment_rainfall_24h": self.packet.rainfall_24h,
                "environment_reported_time": reported_time,
            },
        )
        self._update_inferred_max_hops("TELEMETRY_APP")
