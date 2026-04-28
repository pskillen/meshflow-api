"""Analytics Celery implementations (Neo4j export, daily success snapshots).

Registered Celery names remain on ``traceroute.tasks`` wrappers for beat compatibility.
"""

import logging
from datetime import date, datetime, timedelta

from django.db.models import Count
from django.utils import timezone

from tqdm import tqdm

from traceroute.models import AutoTraceRoute

logger = logging.getLogger(__name__)


def export_traceroutes_to_neo4j_impl():
    """One-off export of all completed AutoTraceRoute records to Neo4j."""
    from traceroute_analytics.neo4j_service import export_all_traceroutes_to_neo4j

    return export_all_traceroutes_to_neo4j()


def push_traceroute_to_neo4j_impl(auto_traceroute_id: int):
    """Push a single completed AutoTraceRoute to Neo4j."""
    from traceroute_analytics.neo4j_service import add_traceroute_edges, get_driver

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


def collect_traceroute_success_for_day(day_date: date, *, skip_existing: bool = False) -> tuple[int, int, int, int]:
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


def collect_traceroute_success_daily_impl():
    """
    Run daily (e.g. 1:05 AM). For the previous calendar day, count completed and failed
    traceroutes and store in StatsSnapshot (stat_type=tr_success_daily).
    """
    yesterday = date.today() - timedelta(days=1)
    _, _, completed, failed = collect_traceroute_success_for_day(yesterday)
    logger.info(
        "collect_traceroute_success_daily: %s completed=%d failed=%d",
        yesterday.isoformat(),
        completed,
        failed,
    )
    return {"date": yesterday.isoformat(), "completed": completed, "failed": failed}


def backfill_traceroute_success_daily_impl(days: int = 30):
    """
    Backfill tr_success_daily snapshots for the last N days.
    Idempotent: skips days that already have snapshots (when run sequentially).
    """
    today = date.today()
    created = 0
    skipped = 0

    for i in tqdm(range(days), unit="day", desc="Backfilling traceroute success"):
        day_date = today - timedelta(days=i + 1)
        c, s, _, _ = collect_traceroute_success_for_day(day_date, skip_existing=True)
        created += c
        skipped += s

    logger.info(
        "Finished backfilling traceroute success daily for the last %d days: created=%d, skipped=%d",
        days,
        created,
        skipped,
    )
    return {"created": created, "skipped": skipped, "days": days}
