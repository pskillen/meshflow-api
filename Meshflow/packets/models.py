"""Models for storing and managing different types of mesh network packets."""

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from constellations.models import MessageChannel
from nodes.models import ManagedNode, RoleSource


class LocationSource(models.IntegerChoices):
    """Location source types for position reports."""

    UNSET = 0, "UNSET"
    MANUAL = 1, "LOC_MANUAL"
    INTERNAL = 2, "LOC_INTERNAL"
    EXTERNAL = 3, "LOC_EXTERNAL"


class RawPacket(models.Model):
    """Base model for storing raw mesh network packets with common attributes."""

    id = models.UUIDField(primary_key=True, null=False, default=uuid.uuid4, editable=False)
    packet_id = models.BigIntegerField(null=False)
    from_int = models.BigIntegerField(null=False)
    from_str = models.CharField(max_length=9, null=True)
    to_int = models.BigIntegerField(null=True)
    to_str = models.CharField(max_length=9, null=True)
    port_num = models.CharField(max_length=50, null=True)
    first_reported_time = models.DateTimeField(null=False, default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["packet_id"]),
            models.Index(fields=["from_int"]),
            models.Index(fields=["from_int", "packet_id"]),
            models.Index(fields=["to_int"]),
        ]
        verbose_name = _("Raw packet")
        verbose_name_plural = _("Raw packets")


class MessagePacket(RawPacket):
    """Model for storing text message packets in the mesh network."""

    message_text = models.TextField(null=False)

    # Used for replies
    reply_packet_id = models.BigIntegerField(null=True, db_index=True)
    emoji = models.BooleanField(null=True)

    class Meta:
        verbose_name = _("Message packet")
        verbose_name_plural = _("Message packets")


class PositionPacket(RawPacket):
    """Model for storing node position data packets."""

    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)
    altitude = models.FloatField(null=True)
    heading = models.FloatField(null=True)
    location_source = models.IntegerField(choices=LocationSource.choices, null=True)
    precision_bits = models.SmallIntegerField(null=True)
    position_time = models.DateTimeField(null=True)  # Unix timestamp converted to datetime
    ground_speed = models.FloatField(null=True)  # in m/s
    ground_track = models.FloatField(null=True)  # in degrees (0-359)

    class Meta:
        verbose_name = _("Position packet")
        verbose_name_plural = _("Position packets")


class NodeInfoPacket(RawPacket):
    """Model for storing node information packets."""

    node_id = models.CharField(max_length=9, null=True, db_index=True)
    short_name = models.CharField(max_length=5, null=True)
    long_name = models.CharField(max_length=50, null=True)
    hw_model = models.CharField(max_length=50, null=True)
    public_key = models.CharField(max_length=64, null=True)
    mac_address = models.CharField(max_length=20, null=True)
    role = models.IntegerField(choices=RoleSource.choices, null=True)
    is_licensed = models.BooleanField(null=True)
    is_unmessagable = models.BooleanField(null=True)

    class Meta:
        verbose_name = _("Node info packet")
        verbose_name_plural = _("Node info packets")


class BaseTelemetryPacket(RawPacket):
    """Base model for all telemetry packet types."""

    reading_time = models.DateTimeField(null=False)

    class Meta:
        abstract = True


class DeviceMetricsPacket(BaseTelemetryPacket):
    """Model for storing device-specific metrics like battery and voltage."""

    battery_level = models.FloatField(null=True)
    voltage = models.FloatField(null=True)
    channel_utilization = models.FloatField(null=True)
    air_util_tx = models.FloatField(null=True)
    uptime_seconds = models.BigIntegerField(null=True)

    class Meta:
        verbose_name = _("Device metrics packet")
        verbose_name_plural = _("Device metrics packets")


class LocalStatsPacket(BaseTelemetryPacket):
    """Model for storing local network statistics."""

    uptime_seconds = models.BigIntegerField(null=True)
    channel_utilization = models.FloatField(null=True)
    air_util_tx = models.FloatField(null=True)
    num_packets_tx = models.BigIntegerField(null=True)
    num_packets_rx = models.BigIntegerField(null=True)
    num_packets_rx_bad = models.BigIntegerField(null=True)
    num_online_nodes = models.IntegerField(null=True)
    num_total_nodes = models.IntegerField(null=True)
    num_rx_dupe = models.BigIntegerField(null=True)
    num_tx_relay = models.BigIntegerField(null=True)
    num_tx_relay_canceled = models.BigIntegerField(null=True)
    heap_total_bytes = models.BigIntegerField(null=True)
    heap_free_bytes = models.BigIntegerField(null=True)
    num_tx_dropped = models.BigIntegerField(null=True)
    noise_floor = models.IntegerField(null=True)

    class Meta:
        verbose_name = _("Local stats packet")
        verbose_name_plural = _("Local stats packets")


class EnvironmentMetricsPacket(BaseTelemetryPacket):
    """Model for storing environmental sensor data."""

    temperature = models.FloatField(null=True)
    relative_humidity = models.FloatField(null=True)
    barometric_pressure = models.FloatField(null=True)
    gas_resistance = models.FloatField(null=True)
    iaq = models.IntegerField(null=True)
    voltage = models.FloatField(null=True)
    current = models.FloatField(null=True)
    distance = models.FloatField(null=True)
    lux = models.FloatField(null=True)
    white_lux = models.FloatField(null=True)
    ir_lux = models.FloatField(null=True)
    uv_lux = models.FloatField(null=True)
    wind_direction = models.IntegerField(null=True)
    wind_speed = models.FloatField(null=True)
    weight = models.FloatField(null=True)
    wind_gust = models.FloatField(null=True)
    wind_lull = models.FloatField(null=True)
    radiation = models.FloatField(null=True)
    rainfall_1h = models.FloatField(null=True)
    rainfall_24h = models.FloatField(null=True)
    soil_moisture = models.IntegerField(null=True)
    soil_temperature = models.FloatField(null=True)

    class Meta:
        verbose_name = _("Environment metrics packet")
        verbose_name_plural = _("Environment metrics packets")


class AirQualityMetricsPacket(BaseTelemetryPacket):
    """Model for storing air quality sensor data."""

    pm10_standard = models.IntegerField(null=True)
    pm25_standard = models.IntegerField(null=True)
    pm100_standard = models.IntegerField(null=True)
    pm10_environmental = models.IntegerField(null=True)
    pm25_environmental = models.IntegerField(null=True)
    pm100_environmental = models.IntegerField(null=True)
    particles_03um = models.IntegerField(null=True)
    particles_05um = models.IntegerField(null=True)
    particles_10um = models.IntegerField(null=True)
    particles_25um = models.IntegerField(null=True)
    particles_50um = models.IntegerField(null=True)
    particles_100um = models.IntegerField(null=True)
    co2 = models.IntegerField(null=True)
    co2_temperature = models.FloatField(null=True)
    co2_humidity = models.FloatField(null=True)
    form_formaldehyde = models.FloatField(null=True)
    form_humidity = models.FloatField(null=True)
    form_temperature = models.FloatField(null=True)
    pm40_standard = models.IntegerField(null=True)
    particles_40um = models.IntegerField(null=True)
    pm_temperature = models.FloatField(null=True)
    pm_humidity = models.FloatField(null=True)
    pm_voc_idx = models.FloatField(null=True)
    pm_nox_idx = models.FloatField(null=True)
    particles_tps = models.FloatField(null=True)

    class Meta:
        verbose_name = _("Air quality metrics packet")
        verbose_name_plural = _("Air quality metrics packets")


class PowerMetricsPacket(BaseTelemetryPacket):
    """Model for storing power metrics (voltage/current per channel)."""

    ch1_voltage = models.FloatField(null=True)
    ch1_current = models.FloatField(null=True)
    ch2_voltage = models.FloatField(null=True)
    ch2_current = models.FloatField(null=True)
    ch3_voltage = models.FloatField(null=True)
    ch3_current = models.FloatField(null=True)
    ch4_voltage = models.FloatField(null=True)
    ch4_current = models.FloatField(null=True)
    ch5_voltage = models.FloatField(null=True)
    ch5_current = models.FloatField(null=True)
    ch6_voltage = models.FloatField(null=True)
    ch6_current = models.FloatField(null=True)
    ch7_voltage = models.FloatField(null=True)
    ch7_current = models.FloatField(null=True)
    ch8_voltage = models.FloatField(null=True)
    ch8_current = models.FloatField(null=True)

    class Meta:
        verbose_name = _("Power metrics packet")
        verbose_name_plural = _("Power metrics packets")


class HealthMetricsPacket(BaseTelemetryPacket):
    """Model for storing health telemetry metrics."""

    heart_bpm = models.IntegerField(null=True)
    spo2 = models.IntegerField(null=True)
    temperature = models.FloatField(null=True)

    class Meta:
        verbose_name = _("Health metrics packet")
        verbose_name_plural = _("Health metrics packets")


class HostMetricsPacket(BaseTelemetryPacket):
    """Model for storing Linux host metrics."""

    uptime_seconds = models.IntegerField(null=True)
    freemem_bytes = models.BigIntegerField(null=True)
    diskfree1_bytes = models.BigIntegerField(null=True)
    diskfree2_bytes = models.BigIntegerField(null=True)
    diskfree3_bytes = models.BigIntegerField(null=True)
    load1 = models.IntegerField(null=True)
    load5 = models.IntegerField(null=True)
    load15 = models.IntegerField(null=True)
    user_string = models.TextField(null=True)

    class Meta:
        verbose_name = _("Host metrics packet")
        verbose_name_plural = _("Host metrics packets")


class TrafficManagementStatsPacket(BaseTelemetryPacket):
    """Model for storing traffic management statistics."""

    packets_inspected = models.IntegerField(null=True)
    position_dedup_drops = models.IntegerField(null=True)
    nodeinfo_cache_hits = models.IntegerField(null=True)
    rate_limit_drops = models.IntegerField(null=True)
    unknown_packet_drops = models.IntegerField(null=True)
    hop_exhausted_packets = models.IntegerField(null=True)
    router_hops_preserved = models.IntegerField(null=True)

    class Meta:
        verbose_name = _("Traffic management stats packet")
        verbose_name_plural = _("Traffic management stats packets")


class TraceroutePacket(RawPacket):
    """Model for storing TRACEROUTE_APP packets."""

    route = models.JSONField(default=list, help_text="List of node_ids, path from source to dest")
    route_back = models.JSONField(default=list, help_text="List of node_ids, path from dest back to source")

    class Meta:
        verbose_name = _("Traceroute packet")
        verbose_name_plural = _("Traceroute packets")


class PacketObservation(models.Model):
    """Relates packets to node(s) which observed the packet."""

    packet = models.ForeignKey(RawPacket, on_delete=models.CASCADE, related_name="observations")
    observer = models.ForeignKey(ManagedNode, on_delete=models.CASCADE)

    channel = models.ForeignKey(MessageChannel, on_delete=models.CASCADE, null=True)
    hop_limit = models.SmallIntegerField(null=True)
    hop_start = models.SmallIntegerField(null=True)

    rx_time = models.DateTimeField(null=False)
    rx_rssi = models.FloatField(null=True)
    rx_snr = models.FloatField(null=True)
    upload_time = models.DateTimeField(null=False, default=timezone.now)
    relay_node = models.BigIntegerField(null=True)

    class Meta:
        verbose_name = _("Packet observation")
        verbose_name_plural = _("Packet observations")
