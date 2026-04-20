"""Celery tasks for traceroute scheduling."""

import logging
import os
from datetime import date, datetime, timedelta

from django.db.models import Count
from django.utils import timezone

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from tqdm import tqdm

from .models import AutoTraceRoute
from .source_selection import select_traceroute_source
from .strategy_rotation import pick_strategy_for_feeder, record_strategy_run
from .target_selection import pick_traceroute_target
from .ws_notify import notify_traceroute_status_changed

logger = logging.getLogger(__name__)

FAILED_TR_TIMEOUT_SECONDS = os.environ.get("FAILED_TR_TIMEOUT_SECONDS", 180)
FAILED_TR_TIMEOUT_SECONDS = int(FAILED_TR_TIMEOUT_SECONDS)


@shared_task
def schedule_traceroutes():
    """
    Run periodically (cadence may vary). Pick one eligible ManagedNode via
    ``select_traceroute_source``, rotate target strategy via Redis LRU, pick target,
    create AutoTraceRoute (trigger_type=auto, trigger_source=scheduler), send command.
    """
    channel_layer = get_channel_layer()

    source_node = select_traceroute_source()
    if not source_node:
        logger.info(
            "schedule_traceroutes: no eligible sources (allow_auto_traceroute with "
            "ingestion within SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS)"
        )
        return {"created": 0}

    strategy = pick_strategy_for_feeder(source_node)
    if not strategy:
        logger.debug("schedule_traceroutes: no applicable strategy for node %s", source_node.node_id_str)
        return {"created": 0}

    target_node = pick_traceroute_target(source_node, strategy=strategy)
    if not target_node:
        logger.debug(
            "schedule_traceroutes: no target for node %s strategy=%s",
            source_node.node_id_str,
            strategy,
        )
        return {"created": 0}

    auto_tr = AutoTraceRoute.objects.create(
        source_node=source_node,
        target_node=target_node,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_AUTO,
        triggered_by=None,
        trigger_source="scheduler",
        target_strategy=strategy,
        status=AutoTraceRoute.STATUS_PENDING,
    )
    record_strategy_run(source_node, strategy)

    async_to_sync(channel_layer.group_send)(
        f"node_{source_node.node_id}",
        {
            "type": "node_command",
            "command": {"type": "traceroute", "target": target_node.node_id},
        },
    )

    auto_tr.status = AutoTraceRoute.STATUS_SENT
    auto_tr.save(update_fields=["status"])
    logger.info(
        "schedule_traceroutes: sent TR %s -> %s (id=%s)",
        source_node.node_id_str,
        target_node.node_id_str,
        auto_tr.id,
    )

    return {"created": 1}


@shared_task
def export_traceroutes_to_neo4j():
    """
    One-off export of all completed AutoTraceRoute records to Neo4j.
    Idempotent; can re-run.
    """
    from .neo4j_service import export_all_traceroutes_to_neo4j

    return export_all_traceroutes_to_neo4j()


@shared_task
def push_traceroute_to_neo4j(auto_traceroute_id: int):
    """
    Push a single completed AutoTraceRoute to Neo4j.
    Called when a traceroute completes (from packet receiver).
    """
    from .neo4j_service import add_traceroute_edges, get_driver

    auto_tr = AutoTraceRoute.objects.filter(pk=auto_traceroute_id).first()
    if not auto_tr or auto_tr.status != AutoTraceRoute.STATUS_COMPLETED:
        logger.debug(
            "push_traceroute_to_neo4j: skipping AutoTraceRoute %s (not completed)",
            auto_traceroute_id,
        )
        return {"skipped": True}

    try:
        driver = get_driver()
        add_traceroute_edges(auto_tr, driver=driver)
        return {"pushed": True}
    except Exception as e:
        logger.exception(
            "push_traceroute_to_neo4j: failed for AutoTraceRoute %s: %s",
            auto_traceroute_id,
            e,
        )
        raise


@shared_task
def mark_stale_traceroutes_failed():
    """
    Run every 60 seconds. Mark traceroutes still pending/sent after 180s as failed.
    Broadcast each update to WebSocket clients.
    """
    cutoff = timezone.now() - timedelta(seconds=FAILED_TR_TIMEOUT_SECONDS)
    stale = AutoTraceRoute.objects.filter(
        status__in=[AutoTraceRoute.STATUS_PENDING, AutoTraceRoute.STATUS_SENT],
        triggered_at__lt=cutoff,
    )
    updated = 0
    for auto_tr in stale:
        auto_tr.status = AutoTraceRoute.STATUS_FAILED
        auto_tr.completed_at = timezone.now()
        auto_tr.error_message = f"Timed out after {FAILED_TR_TIMEOUT_SECONDS}s"
        auto_tr.save(update_fields=["status", "completed_at", "error_message"])
        notify_traceroute_status_changed(auto_tr.id, AutoTraceRoute.STATUS_FAILED)
        updated += 1
        logger.info(
            "mark_stale_traceroutes_failed: TR id=%s marked failed (timed out)",
            auto_tr.id,
        )
    return {"updated": updated}


def _collect_traceroute_success_for_day(day_date: date, *, skip_existing: bool = False) -> tuple[int, int, int, int]:
    """
    Collect tr_success_daily snapshot for a single calendar day.
    Returns (created, skipped, completed, failed).
    """
    from stats.models import StatsSnapshot

    day_start = timezone.make_aware(datetime.combine(day_date, datetime.min.time()))
    day_end = day_start + timedelta(days=1)

    if skip_existing:
        if StatsSnapshot.objects.filter(
            stat_type="tr_success_daily",
            constellation__isnull=True,
            recorded_at=day_start,
        ).exists():
            return (0, 1, 0, 0)

    qs = (
        AutoTraceRoute.objects.filter(
            triggered_at__gte=day_start,
            triggered_at__lt=day_end,
            status__in=[AutoTraceRoute.STATUS_COMPLETED, AutoTraceRoute.STATUS_FAILED],
        )
        .values("status")
        .annotate(count=Count("id"))
    )
    counts = {row["status"]: row["count"] for row in qs}
    completed = counts.get(AutoTraceRoute.STATUS_COMPLETED, 0)
    failed = counts.get(AutoTraceRoute.STATUS_FAILED, 0)

    StatsSnapshot.objects.update_or_create(
        stat_type="tr_success_daily",
        constellation=None,
        recorded_at=day_start,
        defaults={
            "value": {
                "date": day_date.isoformat(),
                "completed": completed,
                "failed": failed,
            },
        },
    )
    return (1, 0, completed, failed)


@shared_task
def collect_traceroute_success_daily():
    """
    Run daily (e.g. 1:05 AM). For the previous calendar day, count completed and failed
    traceroutes and store in StatsSnapshot (stat_type=tr_success_daily).
    """
    yesterday = date.today() - timedelta(days=1)
    _, _, completed, failed = _collect_traceroute_success_for_day(yesterday)
    logger.info(
        "collect_traceroute_success_daily: %s completed=%d failed=%d",
        yesterday.isoformat(),
        completed,
        failed,
    )
    return {"date": yesterday.isoformat(), "completed": completed, "failed": failed}


@shared_task
def backfill_traceroute_success_daily(days: int = 30):
    """
    Backfill tr_success_daily snapshots for the last N days.
    Idempotent: skips days that already have snapshots (when run sequentially).
    """
    today = date.today()
    created = 0
    skipped = 0

    for i in tqdm(range(days), unit="day", desc="Backfilling traceroute success"):
        day_date = today - timedelta(days=i + 1)
        c, s, _, _ = _collect_traceroute_success_for_day(day_date, skip_existing=True)
        created += c
        skipped += s

    logger.info(
        "Finished backfilling traceroute success daily for the last %d days: created=%d, skipped=%d",
        days,
        created,
        skipped,
    )
    return {"created": created, "skipped": skipped, "days": days}
