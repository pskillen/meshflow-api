"""Models for traceroute tracking and triggering."""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from nodes.models import ManagedNode, ObservedNode
from packets.models import TraceroutePacket


class TriggerType(models.IntegerChoices):
    """How an ``AutoTraceRoute`` was created (stable integer storage)."""

    USER = 1, _("User")
    EXTERNAL = 2, _("External")
    MONITORING = 3, _("Monitoring")
    NODE_WATCH = 4, _("Node Watch")
    DX_WATCH = 5, _("DX Watch")


class AutoTraceRoute(models.Model):
    """Records each traceroute request (manual or auto) and its result."""

    TRIGGER_TYPE_USER = TriggerType.USER
    TRIGGER_TYPE_EXTERNAL = TriggerType.EXTERNAL
    TRIGGER_TYPE_MONITORING = TriggerType.MONITORING
    TRIGGER_TYPE_NODE_WATCH = TriggerType.NODE_WATCH
    TRIGGER_TYPE_DX_WATCH = TriggerType.DX_WATCH

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    TARGET_STRATEGY_INTRA_ZONE = "intra_zone"
    TARGET_STRATEGY_DX_ACROSS = "dx_across"
    TARGET_STRATEGY_DX_SAME_SIDE = "dx_same_side"
    TARGET_STRATEGY_LEGACY = "legacy"
    TARGET_STRATEGY_MANUAL = "manual"
    TARGET_STRATEGY_CHOICES = [
        (TARGET_STRATEGY_INTRA_ZONE, _("Intra zone")),
        (TARGET_STRATEGY_DX_ACROSS, _("DX across")),
        (TARGET_STRATEGY_DX_SAME_SIDE, _("DX same side")),
        (TARGET_STRATEGY_LEGACY, _("Legacy / unspecified")),
        (TARGET_STRATEGY_MANUAL, _("Manual target")),
    ]

    source_node = models.ForeignKey(
        ManagedNode,
        on_delete=models.CASCADE,
        related_name="traceroutes_sent",
        help_text=_("Node that sent the TR (source)"),
    )
    target_node = models.ForeignKey(
        ObservedNode,
        on_delete=models.CASCADE,
        related_name="traceroutes_received",
        help_text=_("Destination node"),
    )
    trigger_type = models.PositiveSmallIntegerField(choices=TriggerType.choices)
    triggered_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_traceroutes",
        help_text=_("User who triggered (manual only)"),
    )
    trigger_source = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        help_text=_("e.g. scheduler"),
    )
    target_strategy = models.CharField(
        max_length=24,
        choices=TARGET_STRATEGY_CHOICES,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Hypothesis-driven target selection strategy (scheduler or manual analytics)"),
    )
    triggered_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    route = models.JSONField(
        null=True,
        blank=True,
        help_text=_("List of {node_id, snr} from TR response"),
    )
    route_back = models.JSONField(
        null=True,
        blank=True,
        help_text=_("List of {node_id, snr} from TR response (return path)"),
    )
    raw_packet = models.ForeignKey(
        TraceroutePacket,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auto_traceroutes",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = _("Auto traceroute")
        verbose_name_plural = _("Auto traceroutes")
        indexes = [
            models.Index(fields=["source_node"]),
            models.Index(fields=["target_node"]),
            models.Index(fields=["triggered_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["status", "triggered_at"]),
        ]
        permissions = [
            ("trigger_traceroute", "Can trigger traceroute commands"),
        ]

    def __str__(self):
        return f"TR {self.source_node.node_id_str} -> {self.target_node.node_id_str} ({self.status})"
