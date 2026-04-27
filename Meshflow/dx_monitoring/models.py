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


class DxEventTracerouteSkipReason(models.TextChoices):
    NO_ELIGIBLE_SOURCE = "no_eligible_source", _("No eligible source")
    SOURCE_QUEUE_FULL = "source_queue_full", _("Source pending queue full")
    EVENT_COOLDOWN = "event_cooldown", _("Event exploration cooldown")
    TARGET_COOLDOWN = "target_cooldown", _("Target exploration cooldown")
    SOURCE_COOLDOWN = "source_cooldown", _("Source exploration cooldown")
    BASELINE_IN_FLIGHT = "baseline_in_flight", _("Baseline traceroute already covers this source")
    BASELINE_RECENT_SUCCESS = "baseline_recent_success", _("Recent baseline completed for this source")
    BASELINE_FAILURE_COOLDOWN = "baseline_failure_cooldown", _("Baseline failed recently for this source")
    DUPLICATE_DX_WATCH = "duplicate_dx_watch", _("Existing DX_WATCH for this source and target")
    DESTINATION_EXCLUDED = "destination_excluded", _("Destination excluded from DX")
    FANOUT_SATURATED = "fanout_saturated", _("Max exploration sources already covered for this event")


class DxEventTracerouteOutcome(models.TextChoices):
    PENDING = "pending", _("Awaiting traceroute result")
    COMPLETED = "completed", _("Traceroute completed successfully")
    FAILED = "failed", _("Traceroute failed or timed out")
    SKIPPED = "skipped", _("Did not queue a new traceroute")


class DxEventTraceroute(models.Model):
    """Links a :class:`DxEvent` to queued or linked :class:`traceroute.models.AutoTraceRoute` exploration."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        DxEvent,
        on_delete=models.CASCADE,
        related_name="traceroute_explorations",
    )
    auto_traceroute = models.ForeignKey(
        "traceroute.AutoTraceRoute",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dx_event_traceroutes",
    )
    source_node = models.ForeignKey(
        "nodes.ManagedNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dx_event_traceroutes",
    )
    outcome = models.CharField(
        max_length=24,
        choices=DxEventTracerouteOutcome.choices,
        default=DxEventTracerouteOutcome.PENDING,
        db_index=True,
    )
    skip_reason = models.CharField(
        max_length=48,
        choices=DxEventTracerouteSkipReason.choices,
        blank=True,
        default="",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("DX event traceroute exploration")
        verbose_name_plural = _("DX event traceroute explorations")
        indexes = [
            models.Index(fields=["event", "created_at"], name="dx_evtr_event_created_idx"),
            models.Index(fields=["auto_traceroute"], name="dx_evtr_autotr_idx"),
        ]

    def __str__(self):
        return f"dx-ev-tr:{self.event_id}:{self.outcome}"
