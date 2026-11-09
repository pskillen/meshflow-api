"""Per-node silence threshold learned from a node's own packet cadence (#455)."""

from datetime import timedelta
from math import ceil

from django.db.models import Exists, OuterRef

from nodes.models import ObservedNode
from packets.models import MtRawPacket, PacketObservation

from .constants import (
    LEARNED_OFFLINE_HISTORY_DAYS,
    LEARNED_OFFLINE_MAX_PACKETS,
    LEARNED_OFFLINE_MAX_SECONDS,
    LEARNED_OFFLINE_MIN_INTERVALS,
    LEARNED_OFFLINE_MIN_SECONDS,
)

MIN_INTERVALS = LEARNED_OFFLINE_MIN_INTERVALS


def _p90(values: list[float]) -> float:
    """90th percentile, linear interpolation between closest ranks."""
    ordered = sorted(values)
    pos = 0.9 * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def learned_threshold_seconds(gaps: list[float]) -> int | None:
    """3 x p90 of the gaps, clamped to 6 h - 48 h; None with fewer than MIN_INTERVALS gaps."""
    if len(gaps) < MIN_INTERVALS:
        return None
    value = ceil(3 * _p90(gaps))
    return max(LEARNED_OFFLINE_MIN_SECONDS, min(LEARNED_OFFLINE_MAX_SECONDS, value))


def node_gaps(obs: ObservedNode, now) -> list[float]:
    """Seconds between consecutive packets from this node over the last 7 days (newest 5000 packets)."""
    since = now - timedelta(days=LEARNED_OFFLINE_HISTORY_DAYS)
    times = list(
        MtRawPacket.objects.filter(from_int=obs.meshtastic_node_id, first_reported_time__gte=since)
        .filter(Exists(PacketObservation.objects.filter(packet_id=OuterRef("id"), replayed=False)))
        .order_by("-first_reported_time")
        .values_list("first_reported_time", flat=True)[:LEARNED_OFFLINE_MAX_PACKETS]
    )
    times.reverse()
    return [(b - a).total_seconds() for a, b in zip(times, times[1:])]
