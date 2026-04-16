"""Presence state, Discord notify, hooks from packets and traceroute receiver."""

from __future__ import annotations

import logging

from django.db.models import Q

from nodes.models import ObservedNode
from push_notifications.discord import DiscordSendError, send_dm
from traceroute.models import AutoTraceRoute
from users.discord_sync import user_has_verified_discord_dm_target

from .eligibility import user_can_watch

logger = logging.getLogger(__name__)

__all__ = [
    "user_can_watch",
    "clear_presence_on_packet_from_node",
    "on_monitoring_traceroute_completed",
    "notify_watchers_node_offline",
    "notify_watchers_verification_started",
    "monitoring_traceroute_succeeded_since",
]


def clear_presence_on_packet_from_node(observed_node: ObservedNode) -> None:
    """Reset monitoring presence when any packet advances last_heard for this node."""
    from django.utils import timezone

    from .models import NodePresence

    now = timezone.now()
    base = NodePresence.objects.filter(observed_node=observed_node)

    flag_q = (
        Q(verification_started_at__isnull=False)
        | Q(offline_confirmed_at__isnull=False)
        | Q(suspected_offline_at__isnull=False)
        | Q(last_tr_sent__isnull=False)
        | Q(last_zero_sources_at__isnull=False)
        | Q(tr_sent_count__gt=0)
        | Q(is_offline=True)
        | Q(last_verification_notify_at__isnull=False)
    )

    cleared_offline = base.filter(offline_confirmed_at__isnull=False).update(
        verification_started_at=None,
        offline_confirmed_at=None,
        suspected_offline_at=None,
        last_tr_sent=None,
        last_zero_sources_at=None,
        tr_sent_count=0,
        is_offline=False,
        observed_online_at=now,
        last_verification_notify_at=None,
    )
    cleared_other = (
        base.filter(flag_q)
        .filter(offline_confirmed_at__isnull=True)
        .update(
            verification_started_at=None,
            offline_confirmed_at=None,
            suspected_offline_at=None,
            last_tr_sent=None,
            last_zero_sources_at=None,
            tr_sent_count=0,
            is_offline=False,
            last_verification_notify_at=None,
        )
    )
    if cleared_offline or cleared_other:
        logger.debug("mesh_monitoring: cleared presence for observed_node %s", observed_node.node_id_str)


def monitoring_traceroute_succeeded_since(observed_node: ObservedNode, since) -> bool:
    """True if a monitoring TR completed since `since` (including direct path with empty route/route_back)."""
    return AutoTraceRoute.objects.filter(
        target_node=observed_node,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITOR,
        status=AutoTraceRoute.STATUS_COMPLETED,
        triggered_at__gte=since,
    ).exists()


def on_monitoring_traceroute_completed(auto_tr: AutoTraceRoute) -> None:
    """
    When a monitoring TR completes, end verification early (including direct path with empty hops).
    Called from packets receiver after route fields are saved.
    """
    if auto_tr.trigger_type != AutoTraceRoute.TRIGGER_TYPE_MONITOR:
        return
    if auto_tr.status != AutoTraceRoute.STATUS_COMPLETED:
        return

    from django.db import transaction

    from .models import NodePresence

    with transaction.atomic():
        presence = (
            NodePresence.objects.select_for_update()
            .filter(
                observed_node=auto_tr.target_node,
                verification_started_at__isnull=False,
            )
            .first()
        )
        if not presence:
            return
        if auto_tr.triggered_at < presence.verification_started_at:
            return
        presence.verification_started_at = None
        presence.suspected_offline_at = None
        presence.last_tr_sent = None
        presence.last_zero_sources_at = None
        presence.tr_sent_count = 0
        presence.save(
            update_fields=[
                "verification_started_at",
                "suspected_offline_at",
                "last_tr_sent",
                "last_zero_sources_at",
                "tr_sent_count",
            ],
        )
        logger.info(
            "mesh_monitoring: verification cleared by monitor TR id=%s target=%s",
            auto_tr.id,
            auto_tr.target_node.node_id_str,
        )


def notify_watchers_node_offline(observed_node: ObservedNode) -> int:
    """
    DM each distinct watcher with verified Discord settings (deduped by user).
    Returns number of send_dm attempts.
    """
    from django.contrib.auth import get_user_model

    from .models import NodeWatch

    User = get_user_model()
    user_ids = (
        NodeWatch.objects.filter(observed_node=observed_node, enabled=True).values_list("user_id", flat=True).distinct()
    )
    users = User.objects.filter(pk__in=user_ids)
    text = (
        f"Meshflow mesh monitoring: node {observed_node.node_id_str} "
        f"({observed_node.long_name}) appears offline after verification."
    )
    attempted = 0
    for user in users:
        if not user_has_verified_discord_dm_target(user):
            logger.info(
                "mesh_monitoring: skip notify user=%s (Discord not verified)",
                user.pk,
            )
            continue
        attempted += 1
        try:
            send_dm(user.discord_notify_user_id, text)
        except DiscordSendError as e:
            logger.warning(
                "mesh_monitoring: Discord notify failed user=%s: %s",
                user.pk,
                e,
            )
    return attempted


def notify_watchers_verification_started(observed_node: ObservedNode, silence_threshold_seconds: int) -> int:
    """
    DM each distinct watcher that mesh monitoring is starting RF verification (monitor TRs).

    Returns number of send_dm attempts (same semantics as notify_watchers_node_offline).
    """
    from django.conf import settings
    from django.contrib.auth import get_user_model

    from .models import NodeWatch

    User = get_user_model()
    user_ids = (
        NodeWatch.objects.filter(observed_node=observed_node, enabled=True).values_list("user_id", flat=True).distinct()
    )
    users = User.objects.filter(pk__in=user_ids)
    text = (
        f"Meshflow mesh monitoring: starting RF verification (monitoring traceroutes) for node "
        f"{observed_node.node_id_str} ({observed_node.long_name}). "
        f"Silence threshold for this watch is {silence_threshold_seconds} seconds."
    )
    base_url = (getattr(settings, "FRONTEND_URL", None) or "").strip().rstrip("/")
    if base_url:
        text += f"\n\n{base_url}/nodes/{observed_node.node_id}"
    attempted = 0
    for user in users:
        if not user_has_verified_discord_dm_target(user):
            logger.info(
                "mesh_monitoring: skip verification-start notify user=%s (Discord not verified)",
                user.pk,
            )
            continue
        attempted += 1
        try:
            send_dm(user.discord_notify_user_id, text)
        except DiscordSendError as e:
            logger.warning(
                "mesh_monitoring: Discord verification-start notify failed user=%s: %s",
                user.pk,
                e,
            )
    return attempted
