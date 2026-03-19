import binascii
import os
import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from common.mesh_node_helpers import meshtastic_id_to_hex
from constellations.models import MessageChannel


class LocationSource(models.IntegerChoices):
    """Location source types for position reports."""

    UNSET = 0, "UNSET"
    MANUAL = 1, "LOC_MANUAL"
    INTERNAL = 2, "LOC_INTERNAL"
    EXTERNAL = 3, "LOC_EXTERNAL"


class RoleSource(models.IntegerChoices):
    """Role source types for node roles."""

    # Updated per https://github.com/meshtastic/protobufs/blob/master/meshtastic/config.proto
    # on 5 March 2026
    CLIENT = 0, "CLIENT"
    CLIENT_MUTE = 1, "CLIENT_MUTE"
    ROUTER = 2, "ROUTER"
    ROUTER_CLIENT = 3, "ROUTER_CLIENT"  # deprecated
    REPEATER = 4, "REPEATER"  # deprecated
    TRACKER = 5, "TRACKER"
    SENSOR = 6, "SENSOR"
    TAK = 7, "TAK"
    CLIENT_HIDDEN = 8, "CLIENT_HIDDEN"
    LOST_AND_FOUND = 9, "LOST_AND_FOUND"
    TAK_TRACKER = 10, "TAK_TRACKER"
    ROUTER_LATE = 11, "ROUTER_LATE"
    CLIENT_BASE = 12, "CLIENT_BASE"


class ManagedNode(models.Model):
    """Model representing a mesh network node."""

    internal_id = models.UUIDField(primary_key=True, null=False, default=uuid.uuid4, editable=False)
    node_id = models.BigIntegerField(null=False, db_index=True)
    owner = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="owned_nodes",
        help_text=_("The user who owns this node"),
    )
    constellation = models.ForeignKey("constellations.Constellation", on_delete=models.CASCADE, related_name="nodes")
    name = models.CharField(max_length=100, null=False, blank=False)

    default_location_latitude = models.FloatField(null=True, blank=True)
    default_location_longitude = models.FloatField(null=True, blank=True)

    channel_0 = models.ForeignKey(
        "constellations.MessageChannel", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    channel_1 = models.ForeignKey(
        "constellations.MessageChannel", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    channel_2 = models.ForeignKey(
        "constellations.MessageChannel", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    channel_3 = models.ForeignKey(
        "constellations.MessageChannel", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    channel_4 = models.ForeignKey(
        "constellations.MessageChannel", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    channel_5 = models.ForeignKey(
        "constellations.MessageChannel", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    channel_6 = models.ForeignKey(
        "constellations.MessageChannel", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    channel_7 = models.ForeignKey(
        "constellations.MessageChannel", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )

    allow_auto_traceroute = models.BooleanField(
        default=False,
        help_text=_("If True, this node may be used for auto-scheduled traceroutes and manual triggers."),
    )

    class Meta:
        """Model metadata."""

        verbose_name = _("Managed node")
        verbose_name_plural = _("Managed nodes")

    @property
    def node_id_str(self) -> str:
        """Return the node ID in hex format."""
        if not self.node_id:
            return None
        return meshtastic_id_to_hex(self.node_id)

    def __str__(self):
        """Return a string representation of the node, including user's short name if available."""
        return f"{self.node_id_str} {self.name} ({self.owner.username})"

    def get_channel(self, channel_idx: int) -> MessageChannel:
        """Get the channel for the given index."""

        if channel_idx < 0 or channel_idx > 7:
            raise ValueError(f"Invalid channel index: {channel_idx}")

        return getattr(self, f"channel_{channel_idx}")


class ObservedNode(models.Model):
    """Model representing a mesh network node."""

    internal_id = models.UUIDField(primary_key=True, null=False, default=uuid.uuid4, editable=False)
    node_id = models.BigIntegerField(null=False, db_index=True)
    node_id_str = models.CharField(null=False, blank=False, max_length=9, db_index=True)
    mac_addr = models.CharField(max_length=20, null=True, blank=True)
    long_name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=5)

    hw_model = models.CharField(max_length=50, null=True, blank=True)
    public_key = models.CharField(max_length=64, null=True, blank=True)
    role = models.IntegerField(choices=RoleSource.choices, null=True, blank=True)
    is_licensed = models.BooleanField(null=True, blank=True)
    is_unmessagable = models.BooleanField(null=True, blank=True)

    last_heard = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    claimed_by = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="claimed_nodes",
        help_text=_("The user who owns this node"),
        null=True,
        blank=True,
    )

    class Meta:
        """Model metadata."""

        verbose_name = _("Observed node")
        verbose_name_plural = _("Observed nodes")

    def __str__(self):
        """Return a string representation of the node, including user's short name if available."""
        return f"{self.short_name} ({self.node_id_str})"


class NodeLatestStatus(models.Model):
    """Denormalized cache of latest position and device metrics for a node."""

    node = models.OneToOneField(ObservedNode, on_delete=models.CASCADE, related_name="latest_status")

    # Position fields (from Position model)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    altitude = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)
    location_source = models.IntegerField(choices=LocationSource.choices, null=True, blank=True)
    precision_bits = models.SmallIntegerField(null=True, blank=True)
    ground_speed = models.FloatField(null=True, blank=True)
    ground_track = models.FloatField(null=True, blank=True)
    sats_in_view = models.SmallIntegerField(null=True, blank=True)
    pdop = models.FloatField(null=True, blank=True)
    position_reported_time = models.DateTimeField(null=True, blank=True)

    # Device metrics fields (from DeviceMetrics model)
    battery_level = models.FloatField(null=True, blank=True)
    voltage = models.FloatField(null=True, blank=True)
    channel_utilization = models.FloatField(null=True, blank=True)
    air_util_tx = models.FloatField(null=True, blank=True)
    uptime_seconds = models.BigIntegerField(null=True, blank=True)
    metrics_reported_time = models.DateTimeField(null=True, blank=True)

    # Environment metrics fields
    environment_temperature = models.FloatField(null=True, blank=True)
    environment_relative_humidity = models.FloatField(null=True, blank=True)
    environment_barometric_pressure = models.FloatField(null=True, blank=True)
    environment_gas_resistance = models.FloatField(null=True, blank=True)
    environment_iaq = models.IntegerField(null=True, blank=True)
    environment_lux = models.FloatField(null=True, blank=True)
    environment_wind_direction = models.IntegerField(null=True, blank=True)
    environment_wind_speed = models.FloatField(null=True, blank=True)
    environment_radiation = models.FloatField(null=True, blank=True)
    environment_rainfall_1h = models.FloatField(null=True, blank=True)
    environment_rainfall_24h = models.FloatField(null=True, blank=True)
    environment_reported_time = models.DateTimeField(null=True, blank=True)

    # Air quality metrics fields
    air_quality_pm25_standard = models.IntegerField(null=True, blank=True)
    air_quality_co2 = models.IntegerField(null=True, blank=True)
    air_quality_reported_time = models.DateTimeField(null=True, blank=True)

    # Health metrics fields
    health_heart_bpm = models.IntegerField(null=True, blank=True)
    health_spo2 = models.IntegerField(null=True, blank=True)
    health_temperature = models.FloatField(null=True, blank=True)
    health_reported_time = models.DateTimeField(null=True, blank=True)

    # Host metrics fields
    host_uptime_seconds = models.IntegerField(null=True, blank=True)
    host_freemem_bytes = models.BigIntegerField(null=True, blank=True)
    host_reported_time = models.DateTimeField(null=True, blank=True)

    # Power metrics fields
    ch1_voltage = models.FloatField(null=True, blank=True)
    ch1_current = models.FloatField(null=True, blank=True)
    ch2_voltage = models.FloatField(null=True, blank=True)
    ch2_current = models.FloatField(null=True, blank=True)
    ch3_voltage = models.FloatField(null=True, blank=True)
    ch3_current = models.FloatField(null=True, blank=True)
    ch4_voltage = models.FloatField(null=True, blank=True)
    ch4_current = models.FloatField(null=True, blank=True)
    ch5_voltage = models.FloatField(null=True, blank=True)
    ch5_current = models.FloatField(null=True, blank=True)
    ch6_voltage = models.FloatField(null=True, blank=True)
    ch6_current = models.FloatField(null=True, blank=True)
    ch7_voltage = models.FloatField(null=True, blank=True)
    ch7_current = models.FloatField(null=True, blank=True)
    ch8_voltage = models.FloatField(null=True, blank=True)
    ch8_current = models.FloatField(null=True, blank=True)
    power_reported_time = models.DateTimeField(null=True, blank=True)

    inferred_max_hops = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text=_("Inferred from packet hop_start when received; the node's max hops setting."),
    )

    class Meta:
        verbose_name = _("Node latest status")
        verbose_name_plural = _("Node latest statuses")

    def __str__(self):
        return f"Latest status for {self.node}"


class NodeAPIKey(models.Model):
    """Model for API keys that authenticate nodes to the API."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=100)
    constellation = models.ForeignKey(
        "constellations.Constellation",
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    owner = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="owned_api_keys",
        help_text=_("The user who owns this API key"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Node API Key")
        verbose_name_plural = _("Node API Keys")

    def __str__(self):
        return f"{self.name} ({self.constellation.name})"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)

    @classmethod
    def generate_key(cls):
        return binascii.hexlify(os.urandom(20)).decode()


class NodeAuth(models.Model):
    """Model linking API keys to specific nodes they can authenticate."""

    api_key = models.ForeignKey(NodeAPIKey, on_delete=models.CASCADE, related_name="node_links")
    node = models.ForeignKey(ManagedNode, on_delete=models.CASCADE, related_name="api_key_links")

    class Meta:
        unique_together = ("api_key", "node")
        verbose_name = _("Node authentication")
        verbose_name_plural = _("Node authentications")

    def __str__(self):
        return f"{self.api_key.name} - {self.node}"


class BaseNodeItem(models.Model):
    """Base model for node items."""

    node = models.ForeignKey(ObservedNode, on_delete=models.CASCADE)
    logged_time = models.DateTimeField(default=timezone.now)
    reported_time = models.DateTimeField(default=timezone.now)

    class Meta:
        """Model metadata."""

        abstract = True

    def save(self, *args, **kwargs):
        """Ensure timezone-aware datetimes."""
        if self.logged_time and timezone.is_naive(self.logged_time):
            self.logged_time = timezone.make_aware(self.logged_time)
        if self.reported_time and timezone.is_naive(self.reported_time):
            self.reported_time = timezone.make_aware(self.reported_time)
        super().save(*args, **kwargs)


class Position(BaseNodeItem):
    """Model representing a position report from a mesh node."""

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    altitude = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)
    location_source = models.IntegerField(
        choices=LocationSource.choices,
        default=LocationSource.UNSET,
    )
    precision_bits = models.SmallIntegerField(null=True, blank=True)
    ground_speed = models.FloatField(null=True, blank=True, help_text="Speed in m/s")
    ground_track = models.FloatField(null=True, blank=True, help_text="Track in degrees (0-359)")
    sats_in_view = models.SmallIntegerField(null=True, blank=True, help_text="Number of satellites in view")
    pdop = models.FloatField(null=True, blank=True, help_text="Position Dilution of Precision")

    class Meta:
        verbose_name = _("Position")
        verbose_name_plural = _("Positions")
        indexes = [
            models.Index(fields=["node", "-logged_time"], name="idx_node_latest_position"),
        ]

    def __str__(self):
        return f"Position [{self.latitude}, {self.longitude}]"


class DeviceMetrics(BaseNodeItem):
    """Model representing device metrics reported by a mesh node."""

    battery_level = models.FloatField(help_text="Battery level as a percentage")
    voltage = models.FloatField(help_text="Battery voltage in volts")
    channel_utilization = models.FloatField(help_text="Channel utilization as a percentage")
    air_util_tx = models.FloatField(help_text="Air utilization for transmission")
    uptime_seconds = models.BigIntegerField(help_text="Device uptime in seconds")

    class Meta:
        """Model metadata."""

        verbose_name = _("Device metrics")
        verbose_name_plural = _("Device metrics")
        indexes = [
            models.Index(fields=["node", "-logged_time"], name="idx_node_latest_device_metrics"),
        ]

    def __str__(self):
        return f"Device metrics [{self.battery_level}%, {self.voltage}V, {self.uptime_seconds}s]"


class EnvironmentMetrics(BaseNodeItem):
    """Model representing environment metrics reported by a mesh node."""

    temperature = models.FloatField(null=True, blank=True)
    relative_humidity = models.FloatField(null=True, blank=True)
    barometric_pressure = models.FloatField(null=True, blank=True)
    gas_resistance = models.FloatField(null=True, blank=True)
    iaq = models.IntegerField(null=True, blank=True)
    voltage = models.FloatField(null=True, blank=True)
    current = models.FloatField(null=True, blank=True)
    distance = models.FloatField(null=True, blank=True)
    lux = models.FloatField(null=True, blank=True)
    white_lux = models.FloatField(null=True, blank=True)
    ir_lux = models.FloatField(null=True, blank=True)
    uv_lux = models.FloatField(null=True, blank=True)
    wind_direction = models.IntegerField(null=True, blank=True)
    wind_speed = models.FloatField(null=True, blank=True)
    weight = models.FloatField(null=True, blank=True)
    wind_gust = models.FloatField(null=True, blank=True)
    wind_lull = models.FloatField(null=True, blank=True)
    radiation = models.FloatField(null=True, blank=True)
    rainfall_1h = models.FloatField(null=True, blank=True)
    rainfall_24h = models.FloatField(null=True, blank=True)
    soil_moisture = models.IntegerField(null=True, blank=True)
    soil_temperature = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = _("Environment metrics")
        verbose_name_plural = _("Environment metrics")
        indexes = [
            models.Index(fields=["node", "-logged_time"], name="idx_node_latest_env_metrics"),
        ]


class AirQualityMetrics(BaseNodeItem):
    """Model representing air quality metrics reported by a mesh node."""

    pm10_standard = models.IntegerField(null=True, blank=True)
    pm25_standard = models.IntegerField(null=True, blank=True)
    pm100_standard = models.IntegerField(null=True, blank=True)
    pm10_environmental = models.IntegerField(null=True, blank=True)
    pm25_environmental = models.IntegerField(null=True, blank=True)
    pm100_environmental = models.IntegerField(null=True, blank=True)
    particles_03um = models.IntegerField(null=True, blank=True)
    particles_05um = models.IntegerField(null=True, blank=True)
    particles_10um = models.IntegerField(null=True, blank=True)
    particles_25um = models.IntegerField(null=True, blank=True)
    particles_50um = models.IntegerField(null=True, blank=True)
    particles_100um = models.IntegerField(null=True, blank=True)
    co2 = models.IntegerField(null=True, blank=True)
    co2_temperature = models.FloatField(null=True, blank=True)
    co2_humidity = models.FloatField(null=True, blank=True)
    form_formaldehyde = models.FloatField(null=True, blank=True)
    form_humidity = models.FloatField(null=True, blank=True)
    form_temperature = models.FloatField(null=True, blank=True)
    pm40_standard = models.IntegerField(null=True, blank=True)
    particles_40um = models.IntegerField(null=True, blank=True)
    pm_temperature = models.FloatField(null=True, blank=True)
    pm_humidity = models.FloatField(null=True, blank=True)
    pm_voc_idx = models.FloatField(null=True, blank=True)
    pm_nox_idx = models.FloatField(null=True, blank=True)
    particles_tps = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = _("Air quality metrics")
        verbose_name_plural = _("Air quality metrics")
        indexes = [
            models.Index(fields=["node", "-logged_time"], name="idx_node_latest_aq_metrics"),
        ]


class HealthMetrics(BaseNodeItem):
    """Model representing health metrics reported by a mesh node."""

    heart_bpm = models.IntegerField(null=True, blank=True)
    spo2 = models.IntegerField(null=True, blank=True)
    temperature = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = _("Health metrics")
        verbose_name_plural = _("Health metrics")
        indexes = [
            models.Index(fields=["node", "-logged_time"], name="idx_node_latest_health_metrics"),
        ]


class HostMetrics(BaseNodeItem):
    """Model representing host metrics reported by a mesh node (e.g. Linux)."""

    uptime_seconds = models.IntegerField(null=True, blank=True)
    freemem_bytes = models.BigIntegerField(null=True, blank=True)
    diskfree1_bytes = models.BigIntegerField(null=True, blank=True)
    diskfree2_bytes = models.BigIntegerField(null=True, blank=True)
    diskfree3_bytes = models.BigIntegerField(null=True, blank=True)
    load1 = models.IntegerField(null=True, blank=True)
    load5 = models.IntegerField(null=True, blank=True)
    load15 = models.IntegerField(null=True, blank=True)
    user_string = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = _("Host metrics")
        verbose_name_plural = _("Host metrics")
        indexes = [
            models.Index(fields=["node", "-logged_time"], name="idx_node_latest_host_metrics"),
        ]


class PowerMetrics(BaseNodeItem):
    """Model representing power metrics (voltage/current per channel) reported by a mesh node."""

    ch1_voltage = models.FloatField(null=True, blank=True)
    ch1_current = models.FloatField(null=True, blank=True)
    ch2_voltage = models.FloatField(null=True, blank=True)
    ch2_current = models.FloatField(null=True, blank=True)
    ch3_voltage = models.FloatField(null=True, blank=True)
    ch3_current = models.FloatField(null=True, blank=True)
    ch4_voltage = models.FloatField(null=True, blank=True)
    ch4_current = models.FloatField(null=True, blank=True)
    ch5_voltage = models.FloatField(null=True, blank=True)
    ch5_current = models.FloatField(null=True, blank=True)
    ch6_voltage = models.FloatField(null=True, blank=True)
    ch6_current = models.FloatField(null=True, blank=True)
    ch7_voltage = models.FloatField(null=True, blank=True)
    ch7_current = models.FloatField(null=True, blank=True)
    ch8_voltage = models.FloatField(null=True, blank=True)
    ch8_current = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = _("Power metrics")
        verbose_name_plural = _("Power metrics")
        indexes = [
            models.Index(fields=["node", "-logged_time"], name="idx_node_latest_power_metrics"),
        ]


class NodeOwnerClaim(models.Model):
    """Model representing a user's claim to a node. A row in this table does not necessarily
    mean the user owns the node. The node must send a text message with their claim_key, and the
    system must receive that message, before a claim is accepted.
    """

    node = models.ForeignKey(ObservedNode, on_delete=models.CASCADE)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE)
    claim_key = models.CharField(max_length=64, null=False, blank=False)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
