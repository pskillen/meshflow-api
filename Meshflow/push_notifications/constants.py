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


class DiscordNotificationStatus(models.TextChoices):
    """Outcome of a Discord DM attempt."""

    SENT = "sent", _("Sent")
    SKIPPED = "skipped", _("Skipped")
    FAILED = "failed", _("Failed")
