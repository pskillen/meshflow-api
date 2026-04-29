from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from nodes.models import ObservedNode

from .eligibility import user_can_watch


class NodeWatch(models.Model):
    """User opt-in to monitor silence/offline and/or battery for an observed node."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="node_watches",
    )
    observed_node = models.ForeignKey(
        ObservedNode,
        on_delete=models.CASCADE,
        related_name="watches",
    )
    enabled = models.BooleanField(default=True)
    offline_notifications_enabled = models.BooleanField(
        default=True,
        help_text=_("When enabled and watch is enabled, receive offline / verification Discord notifications."),
    )
    battery_notifications_enabled = models.BooleanField(
        default=False,
        help_text=_("When enabled and watch is enabled, receive low-battery Discord notifications."),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Node watch")
        verbose_name_plural = _("Node watches")
        constraints = [
            models.UniqueConstraint(fields=["user", "observed_node"], name="mesh_monitoring_nodewatch_user_node_uniq"),
        ]
        indexes = [
            models.Index(fields=["observed_node", "enabled"]),
        ]

    def clean(self):
        super().clean()
        if self.observed_node_id and self.user_id and not user_can_watch(self.user, self.observed_node):
            raise ValidationError({"observed_node": _("You may only watch nodes you claimed or infrastructure nodes.")})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Watch {self.user_id} -> {self.observed_node_id}"


class NodeMonitoringConfig(models.Model):
    """Per-observed-node durable monitoring settings (thresholds, battery alerts)."""

    observed_node = models.OneToOneField(
        ObservedNode,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="monitoring_config",
    )
    last_heard_offline_after_seconds = models.PositiveIntegerField(
        default=21600,
        help_text=_("Seconds since last_heard before verification may start."),
    )
    battery_alert_enabled = models.BooleanField(default=False)
    battery_alert_threshold_percent = models.PositiveSmallIntegerField(
        default=50,
        validators=[MinValueValidator(5), MaxValueValidator(80)],
    )
    battery_alert_report_count = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Node monitoring config")
        verbose_name_plural = _("Node monitoring configs")

    def clean(self):
        super().clean()
        if self.last_heard_offline_after_seconds is not None and self.last_heard_offline_after_seconds < 1:
            raise ValidationError({"last_heard_offline_after_seconds": _("Must be at least 1 second.")})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"MonitoringConfig {self.observed_node_id}"


class NodePresence(models.Model):
    """Per-observed-node verification / offline / battery alert runtime state (kept off ObservedNode)."""

    observed_node = models.OneToOneField(
        ObservedNode,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="mesh_presence",
    )
    verification_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the current verification traceroute round started."),
    )
    offline_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the node was confirmed offline after failed verification."),
    )
    suspected_offline_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the current mesh-monitoring verification episode started (silence → TR round)."),
    )
    last_tr_sent = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When a monitoring traceroute command was last sent to the mesh for this target."),
    )
    tr_sent_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Monitoring TR sends in the current episode; reset when the node is considered online."),
    )
    last_zero_sources_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When dispatch last found no eligible managed sources for monitoring TR."),
    )
    is_offline = models.BooleanField(
        default=False,
        help_text=_(
            "True after mesh monitoring confirms the node offline (verification window expired). "
            "Cleared when the node is heard again."
        ),
    )
    observed_online_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            "When mesh monitoring last treated the node as online: initial create while heard, "
            "or recovery after confirmed offline."
        ),
    )
    last_verification_notify_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            "When mesh monitoring last sent a Discord DM that verification (monitor TR) had started, "
            "for cooldown against notify spam."
        ),
    )
    battery_below_threshold_report_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Consecutive device-metric reports below the configured battery threshold."),
    )
    battery_alerting_since = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the current below-threshold streak started (first low report in episode)."),
    )
    battery_alert_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When battery alert episode was confirmed (N consecutive low reports); used for UI and dedupe."),
    )
    last_battery_alert_notify_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When mesh monitoring last sent a low-battery Discord DM for this episode."),
    )
    last_battery_recovered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When battery last recovered above threshold."),
    )

    class Meta:
        verbose_name = _("Node presence (mesh monitoring)")
        verbose_name_plural = _("Node presences (mesh monitoring)")

    def __str__(self):
        return f"Presence {self.observed_node_id}"
