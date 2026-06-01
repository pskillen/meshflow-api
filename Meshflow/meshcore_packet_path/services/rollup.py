"""Roll up MeshCore packet observations into path edge buckets and segment rows."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from meshcore_packet_path.models import (
    EdgeKind,
    MeshCorePathEdgeBucket,
    MeshCorePathSegmentResolution,
    SegmentStatus,
)
from meshcore_packets.models import MeshCorePacketObservation


def resolve_backfill_hours(
    *,
    hours: int | None = None,
    days: int | None = None,
    default_hours: int = 24,
) -> int:
    """Convert CLI/Celery backfill args to a single hour count (--days wins over --hours)."""
    if hours is not None and days is not None:
        raise ValueError("Specify only one of hours or days")
    if days is not None:
        return days * 24
    if hours is not None:
        return hours
    return default_hours


def _normalize_hash(segment: str) -> str:
    return str(segment).strip().lower()


@dataclass
class _EdgeAgg:
    packet_ids: set = field(default_factory=set)
    observation_count: int = 0
    snr_values: list[float] = field(default_factory=list)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None

    def add(self, packet_id, seen_at: datetime, snr: float | None) -> None:
        self.packet_ids.add(packet_id)
        self.observation_count += 1
        if snr is not None:
            self.snr_values.append(float(snr))
        if self.first_seen_at is None or seen_at < self.first_seen_at:
            self.first_seen_at = seen_at
        if self.last_seen_at is None or seen_at > self.last_seen_at:
            self.last_seen_at = seen_at


def touch_segment(
    segment_hash: str,
    *,
    hash_size: int | None,
    hash_mode: int | None,
    seen_at: datetime,
) -> None:
    """Create unknown segment row or bump last_seen_at without downgrading manual/resolved rows."""
    normalized = _normalize_hash(segment_hash)
    seg, created = MeshCorePathSegmentResolution.objects.get_or_create(
        hash_mode=hash_mode,
        hash_size=hash_size,
        segment_hash=normalized,
        defaults={
            "status": SegmentStatus.UNKNOWN,
            "source": "",
            "first_seen_at": seen_at,
            "last_seen_at": seen_at,
        },
    )
    if created:
        return
    updates: dict[str, Any] = {}
    if seen_at > seg.last_seen_at:
        updates["last_seen_at"] = seen_at
    if seen_at < seg.first_seen_at:
        updates["first_seen_at"] = seen_at
    if updates:
        MeshCorePathSegmentResolution.objects.filter(pk=seg.pk).update(**updates)


def collect_path_edge_buckets_for_hour(
    hour_start: datetime,
    *,
    skip_existing: bool = False,
) -> dict[str, int]:
    """
    Aggregate hash-chain edges for observations with upload_time in [hour_start, hour_end).

    Returns counts: created, updated, skipped_hours, observations_processed.
    """
    if hour_start.tzinfo is None:
        hour_start = timezone.make_aware(hour_start)
    hour_start = hour_start.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)

    if skip_existing:
        if MeshCorePathEdgeBucket.objects.filter(
            bucket_start=hour_start,
            bucket_size="1h",
        ).exists():
            return {"created": 0, "updated": 0, "skipped_hours": 1, "observations_processed": 0}

    edge_aggs: dict[tuple, _EdgeAgg] = defaultdict(_EdgeAgg)
    observations_processed = 0

    qs = (
        MeshCorePacketObservation.objects.filter(
            upload_time__gte=hour_start,
            upload_time__lt=hour_end,
        )
        .exclude(path_hashes__isnull=True)
        .select_related("observer", "observer__constellation", "packet")
        .iterator(chunk_size=500)
    )

    for obs in qs:
        segments = obs.path_hashes or []
        if not isinstance(segments, list) or len(segments) < 2:
            continue
        observations_processed += 1
        seen_at = obs.upload_time
        hash_mode = obs.path_hash_mode
        hash_size = obs.path_hash_size
        observer_id = obs.observer_id
        constellation_id = obs.observer.constellation_id if obs.observer_id else None

        for seg in segments:
            touch_segment(
                str(seg),
                hash_size=hash_size,
                hash_mode=hash_mode,
                seen_at=seen_at,
            )

        normalized = [_normalize_hash(s) for s in segments]
        for idx in range(len(normalized) - 1):
            from_hash = normalized[idx]
            to_hash = normalized[idx + 1]
            key = (
                hour_start,
                observer_id,
                constellation_id,
                from_hash,
                to_hash,
            )
            edge_aggs[key].add(obs.packet_id, seen_at, obs.rx_snr)

    created = 0
    updated = 0
    for (bucket_start, observer_id, constellation_id, from_hash, to_hash), agg in edge_aggs.items():
        snr_vals = agg.snr_values
        defaults = {
            "packet_count": len(agg.packet_ids),
            "observation_count": agg.observation_count,
            "first_seen_at": agg.first_seen_at,
            "last_seen_at": agg.last_seen_at,
            "min_snr": min(snr_vals) if snr_vals else None,
            "max_snr": max(snr_vals) if snr_vals else None,
            "avg_snr": sum(snr_vals) / len(snr_vals) if snr_vals else None,
        }
        _obj, was_created = MeshCorePathEdgeBucket.objects.update_or_create(
            bucket_start=bucket_start,
            bucket_size="1h",
            from_kind=EdgeKind.HASH,
            to_kind=EdgeKind.HASH,
            from_hash=from_hash,
            to_hash=to_hash,
            observer_id=observer_id,
            constellation_id=constellation_id,
            defaults=defaults,
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return {
        "created": created,
        "updated": updated,
        "skipped_hours": 0,
        "observations_processed": observations_processed,
    }


def collect_path_edge_buckets_for_range(
    start_hour: datetime,
    end_hour: datetime,
    *,
    skip_existing: bool = False,
    show_progress: bool = False,
) -> dict[str, int]:
    """Roll up each hour in [start_hour, end_hour)."""
    from tqdm import tqdm

    totals = {"created": 0, "updated": 0, "skipped_hours": 0, "observations_processed": 0}
    hour = start_hour.replace(minute=0, second=0, microsecond=0)
    end = end_hour.replace(minute=0, second=0, microsecond=0)
    total_hours = max(0, int((end - hour).total_seconds() // 3600))
    hour_iter = range(total_hours)
    if show_progress:
        hour_iter = tqdm(hour_iter, unit="hour", desc="Backfilling path edges")

    cursor = hour
    for _ in hour_iter:
        result = collect_path_edge_buckets_for_hour(cursor, skip_existing=skip_existing)
        for key in totals:
            totals[key] += result.get(key, 0)
        cursor += timedelta(hours=1)
    return totals
