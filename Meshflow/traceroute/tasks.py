"""Celery tasks for traceroute scheduling."""

import logging
import os
from datetime import date, datetime, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from celery import shared_task
from tqdm import tqdm

from .dispatch import TRACEROUTE_MAX_PENDING_PER_SOURCE, pending_count_for_source, try_dispatch_one
from .models import AutoTraceRoute
from .source_selection import eligible_traceroute_sources_ordered
from .strategy_rotation import ordered_strategies_for_feeder, record_strategy_run
from .target_selection import pick_traceroute_target
from .ws_notify import notify_traceroute_status_changed

logger = logging.getLogger(__name__)

FAILED_TR_TIMEOUT_SECONDS = os.environ.get("FAILED_TR_TIMEOUT_SECONDS", 180)
FAILED_TR_TIMEOUT_SECONDS = int(FAILED_TR_TIMEOUT_SECONDS)


@shared_task
def schedule_traceroutes():
    """
    Run periodically (cadence may vary). For each eligible source (LRU order), try
    hypothesis strategies (Redis LRU order), then legacy; first hit creates an
    AutoTraceRoute and sends the command. Avoids stalemate when one strategy never
    finds a target (meshflow-api#196).
    """
    sources = eligible_traceroute_sources_ordered()
    if not sources:
        logger.warning(
            "schedule_traceroutes: no eligible sources (allow_auto_traceroute with "
            "ingestion within SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS)"
        )
        return {"created": 0}

    attempts: list[tuple[str, str, bool]] = []

    for source_node in sources:
        if pending_count_for_source(source_node.pk) >= TRACEROUTE_MAX_PENDING_PER_SOURCE:
            logger.info(
                "schedule_traceroutes: skip %s, pending cap (%d)",
                source_node.node_id_str,
                TRACEROUTE_MAX_PENDING_PER_SOURCE,
            )
            continue
        strategies = ordered_strategies_for_feeder(source_node)
        chosen_strategy: str | None = None
        target_node = None

        for strategy in strategies:
            target_node = pick_traceroute_target(source_node, strategy=strategy)
            attempts.append((source_node.node_id_str, strategy, target_node is not None))
            if target_node:
                chosen_strategy = strategy
                break

        if not target_node:
            target_node = pick_traceroute_target(
                source_node,
                strategy=AutoTraceRoute.TARGET_STRATEGY_LEGACY,
            )
            attempts.append((source_node.node_id_str, "legacy", target_node is not None))

        if not target_node:
            continue

        row_strategy = chosen_strategy or AutoTraceRoute.TARGET_STRATEGY_LEGACY

        at_now = timezone.now()
        auto_tr = AutoTraceRoute.objects.create(
            source_node=source_node,
            target_node=target_node,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
            triggered_by=None,
            trigger_source="scheduler",
            target_strategy=row_strategy,
            status=AutoTraceRoute.STATUS_PENDING,
            earliest_send_at=at_now,
        )
        if chosen_strategy is not None:
            record_strategy_run(source_node, chosen_strategy)
        logger.info(
            "schedule_traceroutes: queued TR %s -> %s strategy=%s (id=%s) for WebSocket dispatch",
            source_node.node_id_str,
            target_node.node_id_str,
            row_strategy,
            auto_tr.id,
        )
        return {"created": 1}

    logger.warning("schedule_traceroutes: cascade exhausted, no TR created: %s", attempts)
    return {"created": 0}


@shared_task
def dispatch_pending_traceroutes():
    """
    Run frequently (e.g. every 15s). Send due ``AutoTraceRoute`` rows to managed nodes over Channels,
    at most one per source per :data:`traceroute.dispatch.DISPATCH_PER_SOURCE_INTERVAL_SEC` by default.
    """
    summary = {"dispatched": 0, "errors": 0}
    for _ in range(2000):
        r = try_dispatch_one()
        o = r.get("outcome")
        if o == "dispatched":
            summary["dispatched"] += 1
        elif o == "error":
            summary["errors"] += 1
        elif o in ("no_row", "all_cooldown"):
            return summary
    return summary


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
    Run every 60 seconds. Mark pending/sent auto-traceroutes as failed after
    :envvar:`FAILED_TR_TIMEOUT_SECONDS` without completion.

    Pending: clock starts at ``earliest_send_at`` (when the row is due in the queue), not ``triggered_at``,
    so work can wait for per-feeder pacing without time-outing first.

    Sent: clock starts at ``dispatched_at`` when set, else ``triggered_at`` for legacy rows.
    """
    now = timezone.now()
    td = timedelta(seconds=FAILED_TR_TIMEOUT_SECONDS)
    cutoff = now - td
    too_old_pending = Q(
        status=AutoTraceRoute.STATUS_PENDING,
        earliest_send_at__lt=now - td,
    )
    too_old_sent_dispatched = Q(
        status=AutoTraceRoute.STATUS_SENT,
        dispatched_at__isnull=False,
        dispatched_at__lt=now - td,
    )
    too_old_sent_legacy = Q(
        status=AutoTraceRoute.STATUS_SENT,
        dispatched_at__isnull=True,
        triggered_at__lt=cutoff,
    )
    stale = AutoTraceRoute.objects.filter(too_old_pending | too_old_sent_dispatched | too_old_sent_legacy)
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
