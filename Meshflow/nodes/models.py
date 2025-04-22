import binascii
import os
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from common.mesh_node_helpers import meshtastic_id_to_hex


class LocationSource(models.TextChoices):
    """Location source types for position reports."""

    UNSET = "0", _("Unset")
    MANUAL = "1", _("Manual")
    INTERNAL = "2", _("Internal")
    EXTERNAL = "3", _("External")


class MeshtasticNode(models.Model):
    """Model representing a mesh network node."""

    internal_id = models.UUIDField(
        primary_key=True, null=False, default=uuid.uuid4, editable=False
    )
    node_id = models.BigIntegerField(null=False)
    mac_addr = models.CharField(max_length=20, null=True, blank=True)
    constellation = models.ForeignKey(
        "constellations.Constellation", on_delete=models.CASCADE, related_name="nodes"
    )
    owner = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="owned_nodes",
        help_text=_("The user who owns this node"),
    )

    long_name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=5)

    hw_model = models.CharField(max_length=50, null=True, blank=True)
    sw_version = models.CharField(max_length=12, null=True, blank=True)
    public_key = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        """Model metadata."""

        verbose_name = _("Node")
        verbose_name_plural = _("Nodes")

    @property
    def node_id_str(self) -> str:
        """Return the node ID in hex format."""
        if not self.node_id:
            return None
        return meshtastic_id_to_hex(self.node_id)

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
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_api_keys",
    )
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

    api_key = models.ForeignKey(
        NodeAPIKey, on_delete=models.CASCADE, related_name="node_links"
    )
    node = models.ForeignKey(
        MeshtasticNode, on_delete=models.CASCADE, related_name="api_key_links"
    )

    class Meta:
        unique_together = ("api_key", "node")
        verbose_name = _("Node authentication")
        verbose_name_plural = _("Node authentications")

    def __str__(self):
        return f"{self.api_key.name} - {self.node}"


class BaseNodeItem(models.Model):
    """Base model for node items."""

    node = models.ForeignKey(
        MeshtasticNode, on_delete=models.CASCADE, related_name="base_node_item_list"
    )
    logged_time = models.DateTimeField()
    reported_time = models.DateTimeField()

    class Meta:
        """Model metadata."""

        abstract = True


class Position(BaseNodeItem):
    """Model representing a position report from a mesh node."""

    latitude = models.FloatField()
    longitude = models.FloatField()
    altitude = models.FloatField()
    heading = models.FloatField()
    location_source = models.CharField(
        max_length=1,
        choices=LocationSource.choices,
        default=LocationSource.UNSET,
    )

    class Meta:
        verbose_name = _("Position")
        verbose_name_plural = _("Positions")

    def __str__(self):
        return f"{self.node} - {self.latitude}, {self.longitude}"


class DeviceMetrics(models.Model):
    """Model representing device metrics reported by a mesh node."""

    class Meta:
        """Model metadata."""

        verbose_name = _("Device metrics")
        verbose_name_plural = _("Device metrics")

    battery_level = models.IntegerField()
    voltage = models.FloatField()
    channel_utilization = models.FloatField()
    air_util_tx = models.FloatField()
    uptime_seconds = models.IntegerField()

    def __str__(self):
        return f"{self.node} - {self.battery_level}%"
