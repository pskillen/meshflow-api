"""Models for storing and managing different types of mesh network packets."""

import uuid

from django.db import models


class RawPacket(models.Model):
    """Base model for storing raw mesh network packets with common attributes."""

    id = models.UUIDField(primary_key=True, null=False, default=uuid.uuid4, editable=False)
    packet_id = models.BigIntegerField(null=False, db_index=True)
    from_int = models.BigIntegerField(null=False, db_index=True)
    from_str = models.CharField(max_length=9, null=True)
    to_int = models.BigIntegerField(null=True, db_index=True)
    to_str = models.CharField(max_length=9, null=True)
    channel = models.SmallIntegerField(null=True, db_index=True)

    decoded_data = models.JSONField(null=True)
    portnum = models.CharField(max_length=50, null=True)

    hop_limit = models.SmallIntegerField(null=True)
    hop_start = models.SmallIntegerField(null=True)

    rx_time = models.DateTimeField(null=False, db_index=True)
    rx_rssi = models.FloatField(null=True)
    rx_snr = models.FloatField(null=True)

    relay_node = models.BigIntegerField(null=True)

    class Meta:
        abstract = True


class EncryptedPacket(RawPacket):
    """Model for storing encrypted mesh network packets."""

    encrypted_data = models.TextField(null=False, blank=True)


class MessagePacket(RawPacket):
    """Model for storing text message packets in the mesh network."""

    message_text = models.TextField(null=False)


class MessageReplyPacket(MessagePacket):
    """Model for storing reply messages with emoji reactions."""

    reply_packet_id = models.BigIntegerField(null=False, db_index=True)
    original_message = models.ForeignKey(
        MessagePacket, null=True, on_delete=models.CASCADE, related_name="reply_to", db_index=True
    )
    emoji = models.CharField(max_length=2, null=True, db_index=True)


class PositionPacket(RawPacket):
    """Model for storing node position data packets."""

    position_data = models.JSONField(null=False)


class NodeInfoPacket(RawPacket):
    """Model for storing node information packets."""

    user_data = models.JSONField(null=False)


@deprecated("Use DeviceMetricsPacket or LocalStatsPacket instead")
class TelemetryPacket(RawPacket):
    """Deprecated model for storing device telemetry data."""

    device_metrics_data = models.JSONField(null=False)
    time = models.DateTimeField(null=False)


class BaseTelemetryPacket(RawPacket):
    """Base model for all telemetry packet types."""

    time = models.DateTimeField(null=False)


class DeviceMetricsPacket(BaseTelemetryPacket):
    """Model for storing device-specific metrics like battery and voltage."""

    batteryLevel = models.FloatField(null=True)
    voltage = models.FloatField(null=True)
    channelUtilization = models.FloatField(null=True)
    airUtilTx = models.FloatField(null=True)
    uptimeSeconds = models.BigIntegerField(null=True)


class LocalStatsPacket(BaseTelemetryPacket):
    """Model for storing local network statistics."""

    uptimeSeconds = models.BigIntegerField(null=True)
    channelUtilization = models.FloatField(null=True)
    airUtilTx = models.FloatField(null=True)
    numPacketsTx = models.BigIntegerField(null=True)
    numPacketsRx = models.BigIntegerField(null=True)
    numPacketsRxBad = models.BigIntegerField(null=True)
    numOnlineNodes = models.IntegerField(null=True)
    numTotalNodes = models.IntegerField(null=True)
    numRxDupe = models.BigIntegerField(null=True)


class EnvironmentMetricsPacket(BaseTelemetryPacket):
    """Model for storing environmental sensor data."""

    temperature = models.FloatField(null=True)
    relativeHumidity = models.FloatField(null=True)
    barometricPressure = models.FloatField(null=True)
    gasResistance = models.FloatField(null=True)
    iaq = models.FloatField(null=True)
