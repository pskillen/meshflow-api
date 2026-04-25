"""
Traceroute WebSocket dispatch: pacing one send per :class:`~ManagedNode` per interval.

Queued rows are ``AutoTraceRoute`` in ``status=pending``; the Celery task locks due rows
and calls ``group_send`` once per source within ``DISPATCH_PER_SOURCE_INTERVAL_SEC``.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import AutoTraceRoute
from .trigger_intervals import MONITORING_TRIGGER_MIN_INTERVAL_SEC
from .ws_notify import notify_traceroute_status_changed

logger = logging.getLogger(__name__)

DISPATCH_PER_SOURCE_INTERVAL_SEC = int(
    os.environ.get("TRACEROUTE_DISPATCH_INTERVAL_SEC", str(MONITORING_TRIGGER_MIN_INTERVAL_SEC))
)
# Upper bound of pending rows per source: drop new scheduled work (see schedule_traceroute helpers).
TRACEROUTE_MAX_PENDING_PER_SOURCE = int(os.environ.get("TRACEROUTE_MAX_PENDING_PER_SOURCE", "20"))
# Batch size when paging through due rows (per page); pages continue until a send or the table is exhausted.
DISPATCH_CANDIDATE_BATCH = int(os.environ.get("TRACEROUTE_DISPATCH_CANDIDATE_BATCH", "200"))
# Safety cap: stop paging after this many rows scanned (in case the queue is huge).
DISPATCH_MAX_SCAN = int(os.environ.get("TRACEROUTE_DISPATCH_MAX_SCAN", "10000"))


def _last_dispatched_at(source_node_id: int) -> timezone.datetime | None:
    m = (
        AutoTraceRoute.objects.filter(source_node_id=source_node_id, dispatched_at__isnull=False)
        .aggregate(m=Max("dispatched_at"))
        .get("m")
    )
    return m


def pending_count_for_source(source_node_id: int) -> int:
    return AutoTraceRoute.objects.filter(
        source_node_id=source_node_id,
        status=AutoTraceRoute.STATUS_PENDING,
    ).count()


def in_dispatch_cooldown_for_source(source_node_id: int, now) -> bool:
    last = _last_dispatched_at(source_node_id)
    if not last:
        return False
    return now < last + timedelta(seconds=DISPATCH_PER_SOURCE_INTERVAL_SEC)


def try_dispatch_one() -> dict:
    """
    Pick one due pending row (or none), optionally skip for per-source cooldown, else send and mark ``sent``.

    Return dict includes ``outcome``: ``dispatched``, ``no_row``, or ``error`` (or ``all_cooldown`` when
    every due row in the table was blocked by the per-source interval, so nothing is sendable this tick).
    """
    now = timezone.now()
    channel_layer = get_channel_layer()
    base = AutoTraceRoute.objects.filter(
        status=AutoTraceRoute.STATUS_PENDING,
        earliest_send_at__lte=now,
    ).order_by("earliest_send_at", "id")
    if not base.exists():
        return {"outcome": "no_row"}
    offset = 0
    saw_cooldown = False
    while offset < DISPATCH_MAX_SCAN:
        id_batch = list(base.values_list("id", flat=True)[offset : offset + DISPATCH_CANDIDATE_BATCH])
        if not id_batch:
            break
        for cid in id_batch:
            with transaction.atomic():
                tr = (
                    AutoTraceRoute.objects.filter(
                        pk=cid,
                        status=AutoTraceRoute.STATUS_PENDING,
                        earliest_send_at__lte=now,
                    )
                    .select_for_update()
                    .select_related("source_node", "target_node")
                    .first()
                )
                if not tr:
                    continue
                if in_dispatch_cooldown_for_source(tr.source_node_id, now):
                    saw_cooldown = True
                    continue
                return _send_and_update(tr, channel_layer)
        if len(id_batch) < DISPATCH_CANDIDATE_BATCH:
            break
        offset += len(id_batch)
    if saw_cooldown and base.exists():
        return {"outcome": "all_cooldown"}
    return {"outcome": "no_row"}


def _node_watch_update_presence(tr: AutoTraceRoute) -> None:
    if tr.trigger_type != AutoTraceRoute.TRIGGER_TYPE_NODE_WATCH:
        return
    from mesh_monitoring.models import NodePresence

    sent_at = timezone.now()
    NodePresence.objects.filter(pk=tr.target_node_id).update(
        last_tr_sent=sent_at,
        tr_sent_count=F("tr_sent_count") + 1,
    )
    logger.info(
        "mesh_monitoring: dispatch updated presence for monitor TR id=%s %s -> %s",
        tr.id,
        tr.source_node.node_id_str,
        tr.target_node.node_id_str,
    )


def _send_and_update(tr: AutoTraceRoute, channel_layer) -> dict:
    if not tr.source_node or not tr.target_node:
        n = (tr.dispatch_attempts or 0) + 1
        tr.dispatch_attempts = n
        tr.dispatch_error = "Missing source or target"
        tr.save(update_fields=["dispatch_attempts", "dispatch_error"])
        return {"outcome": "error", "id": tr.id, "err": "missing_fk"}
    now = timezone.now()
    try:
        async_to_sync(channel_layer.group_send)(
            f"node_{tr.source_node.node_id}",
            {
                "type": "node_command",
                "command": {"type": "traceroute", "target": tr.target_node.node_id},
            },
        )
    except Exception as e:  # noqa: BLE001 — record channel errors for observability
        tr = AutoTraceRoute.objects.get(pk=tr.pk)
        n = (tr.dispatch_attempts or 0) + 1
        tr.dispatch_attempts = n
        tr.dispatch_error = str(e)[:2000]
        tr.save(update_fields=["dispatch_attempts", "dispatch_error"])
        logger.exception("dispatch: channel layer failed for TR id=%s: %s", tr.id, e)
        return {"outcome": "error", "id": tr.id, "err": str(e)}

    tr = AutoTraceRoute.objects.get(pk=tr.pk)
    tr.status = AutoTraceRoute.STATUS_SENT
    tr.dispatched_at = now
    tr.dispatch_error = None
    tr.save(update_fields=["status", "dispatched_at", "dispatch_error"])
    _node_watch_update_presence(tr)
    try:
        notify_traceroute_status_changed(tr.id, tr.status)
    except Exception:  # noqa: BLE001
        logger.debug("notify_traceroute_status_changed after dispatch failed (non-fatal)", exc_info=True)
    logger.info(
        "dispatch: sent TR id=%s %s -> %s (trigger_type=%s)",
        tr.id,
        tr.source_node.node_id_str,
        tr.target_node.node_id_str,
        tr.trigger_type,
    )
    return {"outcome": "dispatched", "id": tr.id}
