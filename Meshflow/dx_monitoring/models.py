import uuid

from django.conf import settings
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


class DxNotificationCategory(models.TextChoices):
    """
    User-selectable categories for DX Discord notifications.
    `all` is not stored on category rows; use :class:`DxNotificationSubscription.all_categories`.
    """

    NEW_DISTANT_NODE = "new_distant_node", _("New distant node")
    RETURNED_DX_NODE = "returned_dx_node", _("Returned DX node after quiet period")
    DISTANT_OBSERVATION = "distant_observation", _("Distant direct/near-direct observation")
    TRACEROUTE_DISTANT_HOP = "traceroute_distant_hop", _("Distant hop from traceroute evidence")
    CONFIRMED_EVENT = "confirmed_event", _("Event reached evidence threshold")
    EVENT_CLOSED_SUMMARY = "event_closed_summary", _("Event closed (summary)")


# Categories that may appear in the granular allow-list (excludes the synthetic "all" concept).
_DX_NOTIF_SUBSCRIPTION_CATEGORY_CHOICES = tuple(
    (c.value, c.label)
    for c in (
        DxNotificationCategory.NEW_DISTANT_NODE,
        DxNotificationCategory.RETURNED_DX_NODE,
        DxNotificationCategory.DISTANT_OBSERVATION,
        DxNotificationCategory.TRACEROUTE_DISTANT_HOP,
        DxNotificationCategory.CONFIRMED_EVENT,
        DxNotificationCategory.EVENT_CLOSED_SUMMARY,
    )
)


class DxNotificationSubscription(models.Model):
    """Per-user opt-in to DX event Discord DMs (requires verified Discord target)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dx_notification_subscription",
    )
    enabled = models.BooleanField(
        default=False,
        help_text=_("When True and Discord is verified, the user can receive category-filtered DMs."),
    )
    all_categories = models.BooleanField(
        default=True,
        help_text=_("When True, all DX notification categories are included."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("DX notification subscription")
        verbose_name_plural = _("DX notification subscriptions")

    def __str__(self):
        return f"dx-notif-sub:{self.user_id}"


class DxNotificationCategorySelection(models.Model):
    """
    When ``subscription.all_categories`` is False, the user must select at least
    one category; each selected value is a row in this table.
    """

    subscription = models.ForeignKey(
        DxNotificationSubscription,
        on_delete=models.CASCADE,
        related_name="category_selections",
    )
    category = models.CharField(max_length=48, db_index=True, choices=_DX_NOTIF_SUBSCRIPTION_CATEGORY_CHOICES)

    class Meta:
        verbose_name = _("DX notification category selection")
        verbose_name_plural = _("DX notification category selections")
        constraints = [models.UniqueConstraint(fields=("subscription", "category"), name="dx_notif_sub_cat_uniq")]


class DxNotificationDelivery(models.Model):
    """
    One row per successful (event, user, category) send for idempotency;
    not used for failed attempts (see DiscordNotificationAudit).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("DxEvent", on_delete=models.CASCADE, related_name="notification_deliveries")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dx_notification_deliveries",
    )
    category = models.CharField(max_length=48, db_index=True, choices=_DX_NOTIF_SUBSCRIPTION_CATEGORY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("DX notification delivery")
        verbose_name_plural = _("DX notification deliveries")
        constraints = [
            models.UniqueConstraint(
                fields=("event", "user", "category"),
                name="dx_notif_deliv_event_user_category_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["user", "category", "created_at"], name="dx_notif_deliv_user_cat_time"),
        ]
