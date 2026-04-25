"""Celery tasks for mesh monitoring presence and monitoring traceroutes."""

import logging
from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer

from nodes.models import ObservedNode
from traceroute.models import AutoTraceRoute

from .constants import (
    DEFAULT_OFFLINE_AFTER_SECONDS,
    notify_verification_start_enabled,
    verification_notify_cooldown_seconds,
    verification_window_seconds,
)
from .models import NodePresence, NodeWatch
from .selection import select_monitoring_sources
from .services import (
    monitoring_traceroute_succeeded_since,
    notify_watchers_node_offline,
    notify_watchers_verification_started,
)

logger = logging.getLogger(__name__)

# Stagger monitoring TR commands to distinct sources (seconds).
MONITORING_TR_STAGGER_SECONDS = 30


@shared_task
def send_monitoring_traceroute_command(auto_traceroute_id: int) -> None:
    """Send WebSocket traceroute command for a pending monitoring AutoTraceRoute."""
    channel_layer = get_channel_layer()
    auto_tr = AutoTraceRoute.objects.select_related("source_node", "target_node").filter(pk=auto_traceroute_id).first()
    if not auto_tr or auto_tr.trigger_type != AutoTraceRoute.TRIGGER_TYPE_NODE_WATCH:
        return
    if auto_tr.status == AutoTraceRoute.STATUS_SENT:
        return
    if auto_tr.status != AutoTraceRoute.STATUS_PENDING:
        return

    async_to_sync(channel_layer.group_send)(
        f"node_{auto_tr.source_node.node_id}",
        {
            "type": "node_command",
            "command": {"type": "traceroute", "target": auto_tr.target_node.node_id},
        },
    )
    auto_tr.status = AutoTraceRoute.STATUS_SENT
    auto_tr.save(update_fields=["status"])
    sent_at = timezone.now()
    NodePresence.objects.filter(pk=auto_tr.target_node_id).update(
        last_tr_sent=sent_at,
        tr_sent_count=F("tr_sent_count") + 1,
    )
    logger.info(
        "mesh_monitoring: sent monitor TR id=%s %s -> %s",
        auto_tr.id,
        auto_tr.source_node.node_id_str,
        auto_tr.target_node.node_id_str,
    )


def _dispatch_monitoring_round(observed: ObservedNode) -> None:
    sources = select_monitoring_sources(observed, max_sources=3)
    if not sources:
        NodePresence.objects.filter(pk=observed.pk).update(last_zero_sources_at=timezone.now())
        logger.warning(
            "mesh_monitoring: no monitoring sources for target %s",
            observed.node_id_str,
        )
        return
    for i, source in enumerate(sources):
        auto_tr = AutoTraceRoute.objects.create(
            source_node=source,
            target_node=observed,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_NODE_WATCH,
            triggered_by=None,
            trigger_source="mesh_monitoring",
            status=AutoTraceRoute.STATUS_PENDING,
        )
        send_monitoring_traceroute_command.apply_async(
            args=[auto_tr.id],
            countdown=i * MONITORING_TR_STAGGER_SECONDS,
        )


@shared_task
def process_node_watch_presence() -> dict:
    """
    Periodic task (~1 min). For each observed node with enabled watches, update presence:
    silence -> verification TR round -> offline confirmed + Discord, or recover.
    """
    now = timezone.now()
    window = timedelta(seconds=verification_window_seconds())

    watched_ids = NodeWatch.objects.filter(enabled=True).values_list("observed_node_id", flat=True).distinct()
    if not watched_ids:
        return {"watched": 0}

    observed_qs = ObservedNode.objects.filter(pk__in=watched_ids).select_related("latest_status")
    processed = 0
    for obs in observed_qs.iterator(chunk_size=100):
        processed += 1
        _process_one_observed_node(obs, now, window)

    return {"watched": processed}


def _process_one_observed_node(obs: ObservedNode, now, window: timedelta) -> None:
    if not NodeWatch.objects.filter(observed_node=obs, enabled=True).exists():
        return

    presence_row = NodePresence.objects.filter(pk=obs.pk).first()
    eff = presence_row.offline_after if presence_row else DEFAULT_OFFLINE_AFTER_SECONDS

    effective_delta = timedelta(seconds=int(eff))
    last_heard = obs.last_heard
    silent = last_heard is None or last_heard < now - effective_delta

    presence, _ = NodePresence.objects.get_or_create(
        observed_node=obs,
        defaults={
            "observed_online_at": now if not silent else None,
            "is_offline": False,
        },
    )
    eff = presence.offline_after

    if not silent:
        had_confirmed_offline = bool(presence.offline_confirmed_at) or presence.is_offline
        if (
            presence.verification_started_at
            or presence.offline_confirmed_at
            or presence.suspected_offline_at
            or presence.last_tr_sent
            or presence.last_zero_sources_at
            or presence.tr_sent_count
            or presence.is_offline
            or presence.last_verification_notify_at
        ):
            presence.verification_started_at = None
            presence.offline_confirmed_at = None
            presence.suspected_offline_at = None
            presence.last_tr_sent = None
            presence.last_zero_sources_at = None
            presence.tr_sent_count = 0
            presence.is_offline = False
            presence.last_verification_notify_at = None
            if had_confirmed_offline:
                presence.observed_online_at = now
            update_fields = [
                "verification_started_at",
                "offline_confirmed_at",
                "suspected_offline_at",
                "last_tr_sent",
                "last_zero_sources_at",
                "tr_sent_count",
                "is_offline",
                "last_verification_notify_at",
            ]
            if had_confirmed_offline:
                update_fields.append("observed_online_at")
            presence.save(update_fields=update_fields)
        return

    if presence.offline_confirmed_at:
        return

    if presence.verification_started_at:
        vs = presence.verification_started_at
        success = False
        if last_heard and last_heard >= vs:
            success = True
        if not success:
            success = monitoring_traceroute_succeeded_since(obs, vs)

        if success:
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
            return

        if now >= vs + window:
            presence.offline_confirmed_at = now
            presence.verification_started_at = None
            presence.is_offline = True
            presence.save(
                update_fields=["offline_confirmed_at", "verification_started_at", "is_offline"],
            )
            notify_watchers_node_offline(obs)
        return

    presence.verification_started_at = now
    presence.suspected_offline_at = now
    presence.tr_sent_count = 0
    presence.last_tr_sent = None
    presence.last_zero_sources_at = None
    presence.save(
        update_fields=[
            "verification_started_at",
            "suspected_offline_at",
            "tr_sent_count",
            "last_tr_sent",
            "last_zero_sources_at",
        ],
    )
    if notify_verification_start_enabled():
        cooldown_td = timedelta(seconds=verification_notify_cooldown_seconds())
        last_nv = presence.last_verification_notify_at
        if last_nv is None or (now - last_nv) >= cooldown_td:
            attempted = notify_watchers_verification_started(obs, int(eff))
            if attempted > 0:
                presence.last_verification_notify_at = now
                presence.save(update_fields=["last_verification_notify_at"])
    _dispatch_monitoring_round(obs)
