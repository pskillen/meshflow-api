from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from nodes.models import ObservedNode

from .eligibility import user_can_watch


class NodeWatch(models.Model):
    """User opt-in to monitor silence/offline for an observed node."""

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
    offline_after = models.PositiveIntegerField(
        default=7200,
        help_text=_("Seconds without packets (last_heard) before verification may start."),
    )
    enabled = models.BooleanField(default=True)
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


class NodePresence(models.Model):
    """Per-observed-node verification / offline state (kept off ObservedNode)."""

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

    class Meta:
        verbose_name = _("Node presence (mesh monitoring)")
        verbose_name_plural = _("Node presences (mesh monitoring)")

    def __str__(self):
        return f"Presence {self.observed_node_id}"
