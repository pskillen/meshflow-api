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

    CLIENT = 0, "CLIENT"
    CLIENT_MUTE = 1, "CLIENT_MUTE"
    CLIENT_HIDDEN = 2, "CLIENT_HIDDEN"
    TRACKER = 3, "TRACKER"
    LOST_AND_FOUND = 4, "LOST_AND_FOUND"
    SENSOR = 5, "SENSOR"
    TAK = 6, "TAK"
    TAK_TRACKER = 7, "TAK_TRACKER"
    REPEATER = 8, "REPEATER"
    ROUTER = 9, "ROUTER"
    ROUTER_LATE = 10, "ROUTER_LATE"


class ManagedNode(models.Model):
    """Model representing a mesh network node."""

    internal_id = models.UUIDField(primary_key=True, null=False, default=uuid.uuid4, editable=False)
    node_id = models.BigIntegerField(null=False)
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
    sw_version = models.CharField(max_length=12, null=True, blank=True)
    public_key = models.CharField(max_length=64, null=True, blank=True)
    role = models.IntegerField(choices=RoleSource.choices, null=True, blank=True)

    last_heard = models.DateTimeField(null=True, blank=True)

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

    def __str__(self):
        return f"Device metrics [{self.battery_level}%, {self.voltage}V, {self.uptime_seconds}s]"


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
