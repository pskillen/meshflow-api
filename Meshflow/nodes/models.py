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


class Constellation(models.Model):
    """Model representing a constellation of mesh nodes."""

    name = models.CharField(max_length=50)


class MeshtasticNode(models.Model):
    """Model representing a mesh network node."""

    internal_id = models.UUIDField(
        primary_key=True, null=False, default=uuid.uuid4, editable=False
    )
    node_id = models.BigIntegerField(null=False)
    mac_addr = models.CharField(max_length=20, null=True, blank=True)
    constellation = models.ForeignKey(
        Constellation, on_delete=models.CASCADE, related_name="nodes"
    )

    long_name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=5)

    hw_model = models.CharField(max_length=50, null=True, blank=True)
    sw_version = models.CharField(max_length=12, null=True, blank=True)
    public_key = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        """Model metadata."""

        verbose_name = "Node"

    @property
    def node_id_str(self) -> str:
        """Return the node ID in hex format."""
        return meshtastic_id_to_hex(self.node_id)

    def __str__(self):
        """Return a string representation of the node, including user's short name if available."""

        if self.short_name:
            return f"{self.short_name} [{self.node_id_str}]"
        return self.node_id_str


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

    def __str__(self):
        """Return a string representation of the position report."""
        return f"{self.node.id} - {self.logged_time}"


class DeviceMetrics(models.Model):
    """Model representing device metrics reported by a mesh node."""

    class Meta:
        """Model metadata."""

        verbose_name = "Device metrics"
        verbose_name_plural = "Device metrics"

    battery_level = models.IntegerField()
    voltage = models.FloatField()
    channel_utilization = models.FloatField()
    air_util_tx = models.FloatField()
    uptime_seconds = models.IntegerField()

    def __str__(self):
        """Return a string representation of the device metrics report."""
        return f"{self.node.id} - {self.logged_time}"
