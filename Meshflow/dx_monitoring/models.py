import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class DxReasonCode(models.TextChoices):
    NEW_DISTANT_NODE = "new_distant_node", _("New distant node")
    RETURNED_DX_NODE = "returned_dx_node", _("Returned DX node")
    DISTANT_OBSERVATION = "distant_observation", _("Distant observation")
    TRACEROUTE_DISTANT_HOP = "traceroute_distant_hop", _("Traceroute distant hop")


class DxEventState(models.TextChoices):
    ACTIVE = "active", _("Active")
    CLOSED = "closed", _("Closed")


class DxNodeMetadata(models.Model):
    """Per-observed-node flags for DX detection tuning and gating."""

    observed_node = models.OneToOneField(
        "nodes.ObservedNode",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="dx_metadata",
    )
    exclude_from_detection = models.BooleanField(
        default=False,
        help_text=_("When True, this node is ignored by DX candidate detection."),
    )
    exclude_notes = models.TextField(blank=True, default="")
    cluster_position_evaluated_for_dx = models.BooleanField(
        default=False,
        help_text=_(
            "True after the first time the node had usable coordinates and a "
            "constellation cluster footprint existed for cluster-distance evaluation."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("DX node metadata")
        verbose_name_plural = _("DX node metadata")

    def __str__(self):
        return f"dx-meta:{self.observed_node_id}"


class DxEvent(models.Model):
    """Deduplicated DX candidate window for one constellation, destination, and reason."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    constellation = models.ForeignKey(
        "constellations.Constellation",
        on_delete=models.CASCADE,
        related_name="dx_events",
    )
    destination = models.ForeignKey(
        "nodes.ObservedNode",
        on_delete=models.CASCADE,
        related_name="dx_events",
    )
    reason_code = models.CharField(max_length=64, choices=DxReasonCode.choices, db_index=True)
    state = models.CharField(
        max_length=16,
        choices=DxEventState.choices,
        default=DxEventState.ACTIVE,
    )
    first_observed_at = models.DateTimeField()
    last_observed_at = models.DateTimeField()
    active_until = models.DateTimeField(db_index=True)
    observation_count = models.PositiveIntegerField(default=0)
    last_observer = models.ForeignKey(
        "nodes.ManagedNode",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dx_events_last_observed",
    )
    best_distance_km = models.FloatField(null=True, blank=True)
    last_distance_km = models.FloatField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("DX event")
        verbose_name_plural = _("DX events")
        indexes = [
            models.Index(
                fields=["constellation", "destination", "reason_code", "active_until"],
                name="dx_event_lookup_idx",
            ),
        ]

    def __str__(self):
        return f"{self.reason_code}:{self.destination_id}"


class DxEventObservation(models.Model):
    """Packet-level evidence attached to a DX event."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(DxEvent, on_delete=models.CASCADE, related_name="observations")
    raw_packet = models.ForeignKey(
        "packets.RawPacket",
        on_delete=models.CASCADE,
        related_name="dx_event_observations",
    )
    packet_observation = models.ForeignKey(
        "packets.PacketObservation",
        on_delete=models.CASCADE,
        related_name="dx_event_observations",
    )
    observer = models.ForeignKey(
        "nodes.ManagedNode",
        on_delete=models.CASCADE,
        related_name="dx_event_observations",
    )
    observed_at = models.DateTimeField()
    distance_km = models.FloatField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("DX event observation")
        verbose_name_plural = _("DX event observations")
        indexes = [
            models.Index(fields=["event", "observed_at"], name="dx_evobs_event_time_idx"),
        ]

    def __str__(self):
        return f"dx-obs:{self.event_id}:{self.raw_packet_id}"
