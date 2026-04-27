"""Models for push notification delivery audit."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .constants import DiscordNotificationFeature, DiscordNotificationKind, DiscordNotificationStatus


class DiscordNotificationAudit(models.Model):
    """
    One row per Discord DM decision (sent, skipped before send, or failed after attempt).

    Generic enough for mesh monitoring (node watch) and future DX monitoring alerts.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    attempted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When a Discord API send was attempted (null for pre-send skips)."),
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When Discord accepted the message (only for sent)."),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="discord_notification_audits",
    )
    feature = models.CharField(
        max_length=32,
        choices=DiscordNotificationFeature.choices,
        db_index=True,
    )
    kind = models.CharField(
        max_length=64,
        choices=DiscordNotificationKind.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=DiscordNotificationStatus.choices,
        db_index=True,
    )

    discord_recipient_id = models.CharField(
        max_length=32,
        blank=True,
        help_text=_("Discord snowflake used or proposed for the DM, when known."),
    )
    reason = models.TextField(
        blank=True,
        help_text=_("Skip or failure explanation."),
    )
    message_preview = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("Truncated message body for admin review."),
    )

    related_app_label = models.CharField(max_length=64, blank=True)
    related_model_name = models.CharField(max_length=64, blank=True)
    related_object_id = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("Primary key of the related row as string (supports non-int PKs)."),
    )
    related_context = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Discord notification audit")
        verbose_name_plural = _("Discord notification audits")
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["user", "status", "created_at"]),
            models.Index(fields=["feature", "kind", "created_at"]),
        ]

    def __str__(self):
        return f"{self.feature}/{self.kind} {self.status} user={self.user_id}"
