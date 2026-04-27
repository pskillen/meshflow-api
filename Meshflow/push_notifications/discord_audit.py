"""Record Discord DM outcomes for auditing; failures here must not break callers."""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from .constants import DiscordNotificationStatus
from .discord import DiscordSendError, send_dm
from .models import DiscordNotificationAudit

logger = logging.getLogger(__name__)

MESSAGE_PREVIEW_MAX_LEN = 500


def message_preview(content: str, *, max_len: int = MESSAGE_PREVIEW_MAX_LEN) -> str:
    text = (content or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _safe_create_audit(**kwargs: Any) -> DiscordNotificationAudit | None:
    try:
        return DiscordNotificationAudit.objects.create(**kwargs)
    except Exception:
        logger.exception("push_notifications: DiscordNotificationAudit create failed")
        return None


def record_discord_notification_skip(
    *,
    feature: str,
    kind: str,
    user,
    reason: str,
    message_preview_text: str = "",
    discord_recipient_id: str = "",
    related_app_label: str = "",
    related_model_name: str = "",
    related_object_id: str = "",
    related_context: dict | None = None,
) -> DiscordNotificationAudit | None:
    """Persist a skipped Discord DM (e.g. user not verified for DMs)."""
    return _safe_create_audit(
        user=user,
        feature=feature,
        kind=kind,
        status=DiscordNotificationStatus.SKIPPED,
        discord_recipient_id=(discord_recipient_id or "").strip()[:32],
        reason=reason,
        message_preview=message_preview(message_preview_text),
        related_app_label=related_app_label or "",
        related_model_name=related_model_name or "",
        related_object_id=str(related_object_id or "")[:64],
        related_context=related_context or {},
    )


def send_discord_dm_with_audit(
    *,
    feature: str,
    kind: str,
    user,
    discord_user_id: str,
    content: str,
    related_app_label: str = "",
    related_model_name: str = "",
    related_object_id: str = "",
    related_context: dict | None = None,
) -> None:
    """
    Send a Discord DM and record sent vs failed audit rows.

    Re-raises DiscordSendError after recording failure. Audit DB errors are swallowed.
    """
    preview = message_preview(content)
    rid = (discord_user_id or "").strip()[:32]
    base = {
        "user": user,
        "feature": feature,
        "kind": kind,
        "discord_recipient_id": rid,
        "message_preview": preview,
        "related_app_label": related_app_label or "",
        "related_model_name": related_model_name or "",
        "related_object_id": str(related_object_id or "")[:64],
        "related_context": related_context or {},
    }
    now = timezone.now()
    try:
        send_dm(discord_user_id, content)
    except DiscordSendError as exc:
        _safe_create_audit(
            **base,
            status=DiscordNotificationStatus.FAILED,
            attempted_at=now,
            reason=str(exc),
        )
        raise
    _safe_create_audit(
        **base,
        status=DiscordNotificationStatus.SENT,
        attempted_at=now,
        sent_at=now,
        reason="",
    )


__all__ = [
    "message_preview",
    "record_discord_notification_skip",
    "send_discord_dm_with_audit",
]
