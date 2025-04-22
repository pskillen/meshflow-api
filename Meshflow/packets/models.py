"""Models for storing and managing different types of mesh network packets."""

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from nodes.models import MeshtasticNode


class RawPacket(models.Model):
    """Base model for storing raw mesh network packets with common attributes."""

    id = models.UUIDField(
        primary_key=True, null=False, default=uuid.uuid4, editable=False
    )
    packet_id = models.BigIntegerField(null=False)
    from_int = models.BigIntegerField(null=False)
    from_str = models.CharField(max_length=9, null=True)
    to_int = models.BigIntegerField(null=True)
    to_str = models.CharField(max_length=9, null=True)
    port_num = models.CharField(max_length=50, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['packet_id']),
            models.Index(fields=['from_int']),
            models.Index(fields=['to_int']),
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
    location_source = models.CharField(max_length=15, null=True)
    precision_bits = models.SmallIntegerField(null=True)

    class Meta:
        verbose_name = _("Position packet")
        verbose_name_plural = _("Position packets")


class NodeInfoPacket(RawPacket):
    """Model for storing node information packets."""

    node_id = models.CharField(max_length=9, null=True, db_index=True)
    short_name = models.CharField(max_length=5, null=True)
    long_name = models.CharField(max_length=50, null=True)
    hw_model = models.CharField(max_length=50, null=True)
    sw_version = models.CharField(max_length=12, null=True)
    public_key = models.CharField(max_length=64, null=True)
    mac_address = models.CharField(max_length=20, null=True)

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

    class Meta:
        verbose_name = _("Local stats packet")
        verbose_name_plural = _("Local stats packets")


class EnvironmentMetricsPacket(BaseTelemetryPacket):
    """Model for storing environmental sensor data."""

    temperature = models.FloatField(null=True)
    relative_humidity = models.FloatField(null=True)
    barometric_pressure = models.FloatField(null=True)
    gas_resistance = models.FloatField(null=True)
    iaq = models.FloatField(null=True)

    class Meta:
        verbose_name = _("Environment metrics packet")
        verbose_name_plural = _("Environment metrics packets")


class PacketObservation(models.Model):
    """Relates packets to node(s) which observed the packet."""

    packet = models.ForeignKey(RawPacket, on_delete=models.CASCADE)
    node = models.ForeignKey(MeshtasticNode, on_delete=models.CASCADE)

    channel = models.SmallIntegerField(null=True)
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
