"""Celery tasks for stats snapshot collection."""

import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

from django.db.models import Count, Q
from django.utils import timezone

from celery import shared_task
from tqdm import tqdm

from constellations.models import Constellation
from nodes.models import ObservedNode
from packets.models import PacketObservation, RawPacket

from .models import StatsSnapshot

logger = logging.getLogger(__name__)

ONLINE_NODE_WINDOW_HOURS = int(os.environ.get("ONLINE_NODE_WINDOW_HOURS", "2"))


def _get_last_run_started_at() -> Optional[datetime]:
    """Return the recorded_at of the most recent new_nodes (global) snapshot, or None."""
    last = (
        StatsSnapshot.objects.filter(stat_type="new_nodes", constellation__isnull=True)
        .order_by("-recorded_at")
        .values("recorded_at")
        .first()
    )
    return last["recorded_at"] if last else None


def _snapshot_exists(recorded_at: datetime, stat_type: str, constellation_id: Optional[int]) -> bool:
    """Check if a snapshot already exists. Used for idempotent backfill."""
    qs = StatsSnapshot.objects.filter(recorded_at=recorded_at, stat_type=stat_type)
    if constellation_id is None:
        qs = qs.filter(constellation__isnull=True)
    else:
        qs = qs.filter(constellation_id=constellation_id)
    return qs.exists()


def _collect_online_nodes(
    recorded_at: datetime,
    *,
    run_id: Optional[uuid.UUID] = None,
    skip_existing: bool = False,
    use_raw_packet_for_global: bool = False,
) -> tuple[int, int]:
    """
    Collect online_nodes snapshots (hourly) for global and per-constellation.
    Uses threshold = recorded_at - ONLINE_NODE_WINDOW_HOURS for consistency.
    Returns (created, skipped).

    When use_raw_packet_for_global=True, derives global count from RawPacket
    (distinct from_int in window) instead of ObservedNode.last_heard. Use for
    backfill when last_heard may not extend far back (e.g. bulk-imported packets).
    """
    window = timedelta(hours=ONLINE_NODE_WINDOW_HOURS)
    threshold = recorded_at - window
    created = 0
    skipped = 0

    # Global: ObservedNode.last_heard or RawPacket-based (for backfill)
    if skip_existing and _snapshot_exists(recorded_at, "online_nodes", None):
        skipped += 1
    else:
        if use_raw_packet_for_global:
            # Derive from RawPacket for historical hours when last_heard may be incomplete.
            # Window [threshold, recorded_at] = nodes heard in the 2h before the hour boundary.
            global_count = (
                RawPacket.objects.filter(
                    from_int__isnull=False,
                    first_reported_time__gte=threshold,
                    first_reported_time__lte=recorded_at,
                )
                .values_list("from_int", flat=True)
                .distinct()
                .count()
            )
        else:
            global_count = ObservedNode.objects.filter(last_heard__gte=threshold).count()
        StatsSnapshot.objects.create(
            recorded_at=recorded_at,
            stat_type="online_nodes",
            constellation=None,
            value={"count": global_count, "window_hours": ONLINE_NODE_WINDOW_HOURS},
            run_id=run_id,
        )
        created += 1

    # Per-constellation: distinct nodes via PacketObservation
    for constellation in Constellation.objects.all():
        if skip_existing and _snapshot_exists(recorded_at, "online_nodes", constellation.id):
            skipped += 1
        else:
            count = (
                PacketObservation.objects.filter(
                    observer__constellation=constellation,
                    rx_time__gte=threshold,
                )
                .values("packet__from_int")
                .distinct()
                .count()
            )
            StatsSnapshot.objects.create(
                recorded_at=recorded_at,
                stat_type="online_nodes",
                constellation=constellation,
                value={"count": count, "window_hours": ONLINE_NODE_WINDOW_HOURS},
                run_id=run_id,
            )
            created += 1

    return (created, skipped)


PACKET_TYPE_FILTERS = {
    "text_message": Q(messagepacket__isnull=False),
    "position": Q(positionpacket__isnull=False),
    "node_info": Q(nodeinfopacket__isnull=False),
    "device_metrics": Q(devicemetricspacket__isnull=False),
    "local_stats": Q(localstatspacket__isnull=False),
    "environment_metrics": Q(environmentmetricspacket__isnull=False),
    "traceroute": Q(traceroutepacket__isnull=False),
}


def _collect_packet_volume(
    recorded_at: datetime,
    *,
    run_id: Optional[uuid.UUID] = None,
    skip_existing: bool = False,
) -> tuple[int, int]:
    """
    Collect packet_volume snapshot (hourly) for global - count of RawPackets in the hour,
    with per-type breakdown. Returns (created, skipped).
    """
    if skip_existing and _snapshot_exists(recorded_at, "packet_volume", None):
        return (0, 1)

    hour_end = recorded_at + timedelta(hours=1)
    base_qs = RawPacket.objects.filter(
        first_reported_time__gte=recorded_at,
        first_reported_time__lt=hour_end,
    )

    annotate_kwargs = {f"_{k}": Count("id", filter=v) for k, v in PACKET_TYPE_FILTERS.items()}
    agg = base_qs.aggregate(**annotate_kwargs)

    by_type = {k: agg[f"_{k}"] for k in PACKET_TYPE_FILTERS}
    total = base_qs.count()

    StatsSnapshot.objects.create(
        recorded_at=recorded_at,
        stat_type="packet_volume",
        constellation=None,
        value={"count": total, "by_type": by_type},
        run_id=run_id,
    )
    return (1, 0)


def _collect_new_nodes(
    recorded_at: datetime,
    *,
    run_id: Optional[uuid.UUID] = None,
    skip_existing: bool = False,
    last_run_started_at: Optional[datetime] = None,
    for_backfill: bool = False,
) -> tuple[int, int]:
    """
    Collect new_nodes snapshots for global and per-constellation.
    Returns (created, skipped).

    When for_backfill=True: counts nodes with created_at in [recorded_at, recorded_at+1h).
    When for_backfill=False: counts nodes with created_at >= last_run_started_at (delta since last run).
    """
    hour_end = recorded_at + timedelta(hours=1)
    created = 0
    skipped = 0

    if for_backfill:
        # Hour window: nodes created in [recorded_at, hour_end)
        global_filter = {"created_at__gte": recorded_at, "created_at__lt": hour_end}

        def per_constellation_filter(obs_node_ids):
            return ObservedNode.objects.filter(
                node_id__in=obs_node_ids,
                created_at__gte=recorded_at,
                created_at__lt=hour_end,
            )

    else:
        # Delta since last run
        if last_run_started_at is not None:
            global_filter = {"created_at__gte": last_run_started_at}

            def per_constellation_filter(obs_node_ids):
                return ObservedNode.objects.filter(
                    node_id__in=obs_node_ids,
                    created_at__gte=last_run_started_at,
                )

        else:
            global_filter = {"created_at__isnull": False}

            def per_constellation_filter(obs_node_ids):
                return ObservedNode.objects.filter(
                    node_id__in=obs_node_ids,
                    created_at__isnull=False,
                )

    # Global
    if skip_existing and _snapshot_exists(recorded_at, "new_nodes", None):
        skipped += 1
    else:
        count = ObservedNode.objects.filter(**global_filter).count()
        StatsSnapshot.objects.create(
            recorded_at=recorded_at,
            stat_type="new_nodes",
            constellation=None,
            value={"count": count},
            run_id=run_id,
        )
        created += 1

    # Per-constellation
    for constellation in Constellation.objects.all():
        if skip_existing and _snapshot_exists(recorded_at, "new_nodes", constellation.id):
            skipped += 1
        else:
            if for_backfill:
                observed_node_ids = (
                    PacketObservation.objects.filter(observer__constellation=constellation)
                    .values_list("packet__from_int", flat=True)
                    .distinct()
                )
            else:
                if last_run_started_at is not None:
                    observed_node_ids = (
                        PacketObservation.objects.filter(
                            observer__constellation=constellation,
                            rx_time__gte=last_run_started_at,
                        )
                        .values_list("packet__from_int", flat=True)
                        .distinct()
                    )
                else:
                    observed_node_ids = (
                        PacketObservation.objects.filter(observer__constellation=constellation)
                        .values_list("packet__from_int", flat=True)
                        .distinct()
                    )
            count = per_constellation_filter(observed_node_ids).count()
            StatsSnapshot.objects.create(
                recorded_at=recorded_at,
                stat_type="new_nodes",
                constellation=constellation,
                value={"count": count},
                run_id=run_id,
            )
            created += 1

    return (created, skipped)


@shared_task
def collect_stats_snapshots():
    """
    Run periodically (hourly). Collect online_nodes (hourly), packet_volume, and new_nodes (per-run)
    snapshots for global and per-constellation scope.

    Records the *completed* previous hour (not the current hour), since the current hour
    has only just started when this runs at minute 5.
    """
    run_id = uuid.uuid4()
    current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    hour_start = current_hour - timedelta(hours=1)  # Record completed previous hour
    last_run_started_at = _get_last_run_started_at()

    created = 0
    c, _ = _collect_online_nodes(hour_start, run_id=run_id)
    created += c
    c, _ = _collect_packet_volume(hour_start, run_id=run_id)
    created += c
    c, _ = _collect_new_nodes(hour_start, run_id=run_id, last_run_started_at=last_run_started_at)
    created += c

    logger.info(
        "collect_stats_snapshots: completed run_id=%s, created=%d",
        run_id,
        created,
    )
    return {"created": created, "run_id": str(run_id)}


@shared_task
def backfill_stats_snapshots(days: int = 30):
    """
    Backfill online_nodes, packet_volume, and new_nodes snapshots for the last N days.
    Idempotent: skips hours that already have snapshots (when run sequentially).
    """
    now = timezone.now()
    run_id = uuid.uuid4()
    end_hour = now.replace(minute=0, second=0, microsecond=0)
    start_hour = end_hour - timedelta(days=days)

    created = 0
    skipped = 0
    total_hours = int((end_hour - start_hour).total_seconds() / 3600)

    for i in tqdm(range(total_hours), unit="stats", desc="Backfilling stats"):
        hour = start_hour + timedelta(hours=i)
        c, s = _collect_online_nodes(hour, run_id=run_id, skip_existing=True, use_raw_packet_for_global=True)
        created += c
        skipped += s

        c2, s2 = _collect_packet_volume(hour, run_id=run_id, skip_existing=True)
        created += c2
        skipped += s2

        c3, s3 = _collect_new_nodes(hour, run_id=run_id, skip_existing=True, for_backfill=True)
        created += c3
        skipped += s3

    logger.info(
        "Finished backfilling stats snapshots for the last %d days: created=%d, skipped=%d",
        days,
        created,
        skipped,
    )
    return {"created": created, "skipped": skipped, "days": days}
