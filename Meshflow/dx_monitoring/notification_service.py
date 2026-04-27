"""DX monitoring Discord notifications: subscriber selection, coalescing, audit logging."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from mesh_monitoring.services import _format_node_label, _node_details_url
from push_notifications.constants import DiscordNotificationFeature, DiscordNotificationKind
from push_notifications.discord import DiscordSendError
from push_notifications.discord_audit import record_discord_notification_skip, send_discord_dm_with_audit
from users.discord_sync import user_has_verified_discord_dm_target

from .models import (
    DxEvent,
    DxNotificationCategory,
    DxNotificationDelivery,
    DxNotificationSubscription,
    DxReasonCode,
)

logger = logging.getLogger(__name__)

DISCORD_MESSAGE_MAX = 2000

# Map detection reason_code to notification / subscription category (same string values).
REASON_CODE_TO_NOTIFICATION_CATEGORY: dict[str, str] = {
    DxReasonCode.NEW_DISTANT_NODE: DxNotificationCategory.NEW_DISTANT_NODE,
    DxReasonCode.RETURNED_DX_NODE: DxNotificationCategory.RETURNED_DX_NODE,
    DxReasonCode.DISTANT_OBSERVATION: DxNotificationCategory.DISTANT_OBSERVATION,
    DxReasonCode.TRACEROUTE_DISTANT_HOP: DxNotificationCategory.TRACEROUTE_DISTANT_HOP,
}

CATEGORY_TO_DISCORD_KIND: dict[str, str] = {
    DxNotificationCategory.NEW_DISTANT_NODE: DiscordNotificationKind.DX_NEW_DISTANT_NODE,
    DxNotificationCategory.RETURNED_DX_NODE: DiscordNotificationKind.DX_RETURNED_NODE,
    DxNotificationCategory.DISTANT_OBSERVATION: DiscordNotificationKind.DX_DISTANT_OBSERVATION,
    DxNotificationCategory.TRACEROUTE_DISTANT_HOP: DiscordNotificationKind.DX_TRACEROUTE_DISTANT_HOP,
    DxNotificationCategory.CONFIRMED_EVENT: DiscordNotificationKind.DX_CONFIRMED_EVENT,
    DxNotificationCategory.EVENT_CLOSED_SUMMARY: DiscordNotificationKind.DX_EVENT_CLOSED_SUMMARY,
}


def discord_kind_for_category(category: str) -> str:
    k = CATEGORY_TO_DISCORD_KIND.get(category)
    if k is None:  # pragma: no cover - preflight in run_notify_dx_event
        return DiscordNotificationKind.DX_NEW_DISTANT_NODE
    return k


def reason_code_to_notification_category(reason_code: str) -> str | None:
    return REASON_CODE_TO_NOTIFICATION_CATEGORY.get(reason_code)


def _category_label(category: str) -> str:
    labels = {c.value: str(c.label) for c in DxNotificationCategory}
    return labels.get(category, category)


def build_dx_discord_message(*, event: DxEvent, category: str) -> str:
    dest = event.destination
    label = _format_node_label(dest)
    const_name = event.constellation.name if event.constellation_id else "—"
    lines = [
        "Meshflow DX monitoring",
        f"Category: {_category_label(category)}",
        f"Destination: {label}",
        f"Constellation: {const_name}",
    ]
    if event.last_observer_id:
        lo = event.last_observer
        if lo is not None:
            lines.append(f"Latest observer: {lo.name or lo.node_id_str}")
    lines.append(f"First seen: {event.first_observed_at.isoformat()}")
    lines.append(f"Last seen: {event.last_observed_at.isoformat()}")
    if event.best_distance_km is not None:
        lines.append(f"Best distance (km): {event.best_distance_km:.1f}")
    elif event.last_distance_km is not None:
        lines.append(f"Last distance (km): {event.last_distance_km:.1f}")
    lines.append(f"Observations: {event.observation_count}")
    url = _node_details_url(dest)
    if url:
        lines.append(url)
    text = "\n".join(lines)
    if len(text) > DISCORD_MESSAGE_MAX:
        text = text[: DISCORD_MESSAGE_MAX - 1] + "…"
    return text


def user_wants_category(sub: DxNotificationSubscription, category: str) -> bool:
    if not sub.enabled:
        return False
    if sub.all_categories:
        return True
    return sub.category_selections.filter(category=category).exists()


def _category_cooldown_exceeded(user_id: int, category: str) -> bool:
    minutes = int(getattr(settings, "DX_MONITORING_NOTIFICATION_CATEGORY_COOLDOWN_MINUTES", 0) or 0)
    if minutes <= 0:
        return True
    since = timezone.now() - timedelta(minutes=minutes)
    return not DxNotificationDelivery.objects.filter(user_id=user_id, category=category, created_at__gte=since).exists()


def run_notify_dx_event(event_id, category: str) -> None:
    """
    Notify subscribed users for one DX event and one notification category.
    Respects idempotency (DxNotificationDelivery), cool-down, and Discord audit.
    """
    if not getattr(settings, "DX_MONITORING_NOTIFICATIONS_ENABLED", False):
        return
    if category not in CATEGORY_TO_DISCORD_KIND:
        logger.warning("dx_monitoring: skip notify unknown category=%s event_id=%s", category, event_id)
        return

    try:
        event = DxEvent.objects.select_related("constellation", "destination", "last_observer").get(pk=event_id)
    except DxEvent.DoesNotExist:
        logger.warning("dx_monitoring: notify missing event_id=%s", event_id)
        return

    kind = discord_kind_for_category(category)
    text = build_dx_discord_message(event=event, category=category)
    related_ctx = {
        "dx_event_id": str(event.pk),
        "category": category,
    }

    subs = DxNotificationSubscription.objects.filter(enabled=True).select_related("user")
    for sub in subs:
        user = sub.user
        if not user_wants_category(sub, category):
            continue
        if DxNotificationDelivery.objects.filter(event=event, user=user, category=category).exists():
            continue
        if not _category_cooldown_exceeded(user.pk, category):
            record_discord_notification_skip(
                feature=DiscordNotificationFeature.DX_MONITORING,
                kind=kind,
                user=user,
                reason="Per-user per-category cool-down (recent send of same category).",
                message_preview_text=text,
                discord_recipient_id=getattr(user, "discord_notify_user_id", "") or "",
                related_app_label="dx_monitoring",
                related_model_name="DxEvent",
                related_object_id=str(event.pk),
                related_context=related_ctx,
            )
            continue
        if not user_has_verified_discord_dm_target(user):
            record_discord_notification_skip(
                feature=DiscordNotificationFeature.DX_MONITORING,
                kind=kind,
                user=user,
                reason="Discord DM target not verified (missing or stale notification settings).",
                message_preview_text=text,
                discord_recipient_id=getattr(user, "discord_notify_user_id", "") or "",
                related_app_label="dx_monitoring",
                related_model_name="DxEvent",
                related_object_id=str(event.pk),
                related_context=related_ctx,
            )
            continue
        try:
            send_discord_dm_with_audit(
                feature=DiscordNotificationFeature.DX_MONITORING,
                kind=kind,
                user=user,
                discord_user_id=user.discord_notify_user_id,
                content=text,
                related_app_label="dx_monitoring",
                related_model_name="DxEvent",
                related_object_id=str(event.pk),
                related_context=related_ctx,
            )
        except DiscordSendError as exc:
            logger.warning("dx_monitoring: Discord notify failed user=%s event=%s: %s", user.pk, event_id, exc)
            continue
        DxNotificationDelivery.objects.get_or_create(
            event=event,
            user=user,
            category=category,
        )


__all__ = [
    "REASON_CODE_TO_NOTIFICATION_CATEGORY",
    "CATEGORY_TO_DISCORD_KIND",
    "build_dx_discord_message",
    "discord_kind_for_category",
    "reason_code_to_notification_category",
    "run_notify_dx_event",
    "user_wants_category",
]
