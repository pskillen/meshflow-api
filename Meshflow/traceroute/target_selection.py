"""Target selection for traceroutes (auto mode)."""

import math
from datetime import timedelta

from django.db.models import Max
from django.utils import timezone

from nodes.models import ManagedNode, ObservedNode

from .models import AutoTraceRoute


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two (lat, lon) points."""
    R = 6371  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _get_source_position(managed_node: ManagedNode) -> tuple[float, float] | None:
    """Get (lat, lon) for ManagedNode: default_location or from ObservedNode."""
    if managed_node.default_location_latitude is not None and managed_node.default_location_longitude is not None:
        return (
            managed_node.default_location_latitude,
            managed_node.default_location_longitude,
        )
    obs = ObservedNode.objects.filter(node_id=managed_node.node_id).select_related("latest_status").first()
    if obs and obs.latest_status and obs.latest_status.latitude is not None:
        return obs.latest_status.latitude, obs.latest_status.longitude
    return None


def _get_last_traced_by_source(managed_node: ManagedNode) -> dict[int, float]:
    """
    Return mapping of target_node_id -> hours since last traced by this ManagedNode.
    Never-traced targets are not in the map (treat as infinite hours ago).
    """
    cutoff = timezone.now() - timedelta(days=30)  # only consider recent TRs
    rows = (
        AutoTraceRoute.objects.filter(
            source_node=managed_node,
            triggered_at__gte=cutoff,
        )
        .values("target_node__node_id")
        .annotate(last_triggered=Max("triggered_at"))
    )
    now = timezone.now()
    return {row["target_node__node_id"]: (now - row["last_triggered"]).total_seconds() / 3600 for row in rows}


def _demerit_hours(hours_since_last: float | None) -> float:
    """
    Demerit (penalty) for a candidate based on how recently it was traced.
    Never traced (None) -> 0. Just traced (0h) -> 50. 24h ago -> 0.
    """
    if hours_since_last is None:
        return 0.0
    if hours_since_last >= 24:
        return 0.0
    return 50.0 * (1.0 - hours_since_last / 24.0)


def pick_traceroute_target(
    managed_node: ManagedNode,
    last_heard_within_hours: int = 3,
    slot: str | None = None,
) -> ObservedNode | None:
    """
    Pick one target ObservedNode for a ManagedNode using geography-aware algorithm.

    - Filter: last_heard within N hours, has latest_status with lat/lon
    - Exclude: source node (self), other ManagedNodes
    - Sort by (distance - demerit) descending: prioritise periphery, demerit recently traced
    - Take top 20, deterministic choice: hash(managed_node_id + date + slot) % 20
    """
    source_pos = _get_source_position(managed_node)
    if not source_pos:
        return None

    cutoff = timezone.now() - timedelta(hours=last_heard_within_hours)
    managed_node_ids = set(ManagedNode.objects.values_list("node_id", flat=True))
    last_traced_hours = _get_last_traced_by_source(managed_node)

    candidates = (
        ObservedNode.objects.filter(
            last_heard__gte=cutoff,
            latest_status__latitude__isnull=False,
            latest_status__longitude__isnull=False,
        )
        .exclude(node_id=managed_node.node_id)
        .exclude(node_id__in=managed_node_ids)
        .select_related("latest_status")
    )

    with_score = []
    for obs in candidates:
        lat = obs.latest_status.latitude
        lon = obs.latest_status.longitude
        dist = _haversine_km(source_pos[0], source_pos[1], lat, lon)
        hours_since = last_traced_hours.get(obs.node_id)
        demerit = _demerit_hours(hours_since)
        score = dist - demerit
        with_score.append((score, obs))

    with_score.sort(key=lambda x: -x[0])  # descending (periphery first, less recently traced)
    top20 = [obs for _, obs in with_score[:20]]
    if not top20:
        return None

    date_str = timezone.now().date().isoformat()
    slot_str = slot or "default"
    h = hash((managed_node.node_id, date_str, slot_str)) % (1 << 32)
    idx = h % len(top20)
    return top20[idx]
