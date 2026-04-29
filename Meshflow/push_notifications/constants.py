"""Shared constants for Discord notification audit and delivery."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class DiscordNotificationFeature(models.TextChoices):
    """High-level product area that triggered a Discord DM decision."""

    NODE_WATCH = "node_watch", _("Node watch (mesh monitoring)")
    DX_MONITORING = "dx_monitoring", _("DX monitoring")


class DiscordNotificationKind(models.TextChoices):
    """Specific notification template / intent."""

    NODE_OFFLINE = "node_offline", _("Node offline (after verification)")
    VERIFICATION_STARTED = "verification_started", _("Mesh monitoring verification started")
    NODE_BATTERY_LOW = "node_battery_low", _("Node battery low (mesh monitoring)")
    # DX monitoring (opt-in; feature flag DX_MONITORING_NOTIFICATIONS_ENABLED)
    DX_NEW_DISTANT_NODE = "dx_new_distant_node", _("DX: new distant node")
    DX_RETURNED_NODE = "dx_returned_node", _("DX: returned node after quiet period")
    DX_DISTANT_OBSERVATION = "dx_distant_observation", _("DX: distant direct observation")
    DX_TRACEROUTE_DISTANT_HOP = "dx_traceroute_distant_hop", _("DX: distant hop from traceroute")
    DX_CONFIRMED_EVENT = "dx_confirmed_event", _("DX: event reached evidence threshold")
    DX_EVENT_CLOSED_SUMMARY = "dx_event_closed_summary", _("DX: event closed summary")


class DiscordNotificationStatus(models.TextChoices):
    """Outcome of a Discord DM attempt."""

    SENT = "sent", _("Sent")
    SKIPPED = "skipped", _("Skipped")
    FAILED = "failed", _("Failed")
