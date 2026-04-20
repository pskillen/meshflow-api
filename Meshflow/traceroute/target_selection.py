"""Target selection for traceroutes (auto mode and strategy-driven hypotheses)."""

from __future__ import annotations

from datetime import timedelta
from statistics import median

from django.db.models import Max
from django.utils import timezone

from common.geo import haversine_km
from constellations.geometry import (
    bearing_difference_deg,
    bearing_from_centroid_to_point,
    constellation_centroid,
    get_constellation_envelope,
    initial_bearing_deg,
)
from mesh_monitoring.suppression import suppressed_observed_node_ids
from nodes.models import ManagedNode, ObservedNode
from nodes.positioning import managed_node_lat_lon

from .models import AutoTraceRoute


def _get_last_traced_by_source(managed_node: ManagedNode) -> dict[int, float]:
    """
    Return mapping of target_node_id -> hours since last traced by this ManagedNode.
    Never-traced targets are not in the map (treat as infinite hours ago).
    """
    cutoff = timezone.now() - timedelta(days=30)
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
    """Penalty for tracing the same target recently (0–50 over 24h)."""
    if hours_since_last is None:
        return 0.0
    if hours_since_last >= 24:
        return 0.0
    return 50.0 * (1.0 - hours_since_last / 24.0)


def _iter_scored_candidates(
    managed_node: ManagedNode,
    last_heard_within_hours: int,
    last_traced_hours: dict[int, float],
    managed_node_ids: set[int],
    suppressed: list[int],
):
    """Yield (score, ObservedNode) where higher score is better (legacy-style)."""
    source_pos = managed_node_lat_lon(managed_node)
    if not source_pos:
        return

    cutoff = timezone.now() - timedelta(hours=last_heard_within_hours)
    candidates = (
        ObservedNode.objects.filter(
            last_heard__gte=cutoff,
            latest_status__latitude__isnull=False,
            latest_status__longitude__isnull=False,
        )
        .exclude(node_id=managed_node.node_id)
        .exclude(node_id__in=managed_node_ids)
        .exclude(pk__in=suppressed)
        .select_related("latest_status")
    )

    for obs in candidates:
        lat = obs.latest_status.latitude
        lon = obs.latest_status.longitude
        dist = haversine_km(source_pos[0], source_pos[1], lat, lon)
        hours_since = last_traced_hours.get(obs.node_id)
        demerit = _demerit_hours(hours_since)
        score = dist - demerit
        yield score, obs


def _deterministic_pick(
    managed_node: ManagedNode,
    ranked: list[ObservedNode],
    slot: str | None,
) -> ObservedNode | None:
    if not ranked:
        return None
    date_str = timezone.now().date().isoformat()
    slot_str = slot or "default"
    h = hash((managed_node.node_id, date_str, slot_str)) % (1 << 32)
    idx = h % len(ranked)
    return ranked[idx]


def pick_traceroute_target(
    managed_node: ManagedNode,
    last_heard_within_hours: int = 3,
    slot: str | None = None,
    strategy: str | None = None,
) -> ObservedNode | None:
    """
    Pick one target ObservedNode for a ManagedNode.

    ``strategy``:
        ``None`` / ``legacy`` — original periphery-first + recency demerit (existing behaviour).
        ``intra_zone`` / ``dx_across`` / ``dx_same_side`` — hypothesis-driven selectors (#176).
    """
    strat = strategy
    if strat == AutoTraceRoute.TARGET_STRATEGY_LEGACY:
        strat = None

    last_traced_hours = _get_last_traced_by_source(managed_node)
    managed_node_ids = set(ManagedNode.objects.values_list("node_id", flat=True))
    suppressed = list(suppressed_observed_node_ids())

    if strat is None:
        return _pick_legacy(
            managed_node,
            last_heard_within_hours,
            last_traced_hours,
            managed_node_ids,
            suppressed,
            slot,
        )

    if strat == AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE:
        return _pick_intra_zone(
            managed_node,
            last_heard_within_hours,
            last_traced_hours,
            managed_node_ids,
            suppressed,
            slot,
        )
    if strat == AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS:
        return _pick_dx(
            managed_node,
            last_heard_within_hours,
            last_traced_hours,
            managed_node_ids,
            suppressed,
            slot,
            across=True,
        )
    if strat == AutoTraceRoute.TARGET_STRATEGY_DX_SAME_SIDE:
        return _pick_dx(
            managed_node,
            last_heard_within_hours,
            last_traced_hours,
            managed_node_ids,
            suppressed,
            slot,
            across=False,
        )

    return _pick_legacy(
        managed_node,
        last_heard_within_hours,
        last_traced_hours,
        managed_node_ids,
        suppressed,
        slot,
    )


def _pick_legacy(
    managed_node,
    last_heard_within_hours,
    last_traced_hours,
    managed_node_ids,
    suppressed,
    slot,
):
    scored = list(
        _iter_scored_candidates(
            managed_node,
            last_heard_within_hours,
            last_traced_hours,
            managed_node_ids,
            suppressed,
        )
    )
    scored.sort(key=lambda x: -x[0])
    top20 = [obs for _, obs in scored[:20]]
    return _deterministic_pick(managed_node, top20, slot)


def _centroid_lat_lon(constellation) -> tuple[float, float] | None:
    env = get_constellation_envelope(constellation)
    if env:
        return env["centroid_lat"], env["centroid_lon"]
    return constellation_centroid(constellation)


def _pick_intra_zone(
    managed_node,
    last_heard_within_hours,
    last_traced_hours,
    managed_node_ids,
    suppressed,
    slot,
):
    constellation = managed_node.constellation
    env = get_constellation_envelope(constellation) if constellation else None
    if env is None:
        return None

    source_pos = managed_node_lat_lon(managed_node)
    if not source_pos:
        return None

    c_lat, c_lon = env["centroid_lat"], env["centroid_lon"]
    r_km = env["radius_km"]

    inside: list[tuple[float, ObservedNode]] = []
    for score, obs in _iter_scored_candidates(
        managed_node,
        last_heard_within_hours,
        last_traced_hours,
        managed_node_ids,
        suppressed,
    ):
        lat = obs.latest_status.latitude
        lon = obs.latest_status.longitude
        d_centroid = haversine_km(c_lat, c_lon, lat, lon)
        if d_centroid <= r_km:
            d_src = haversine_km(source_pos[0], source_pos[1], lat, lon)
            inside.append((d_src, obs))

    if not inside:
        return None

    dists = [d for d, _ in inside]
    med = float(median(dists))
    scored = []
    for d_src, obs in inside:
        hours_since = last_traced_hours.get(obs.node_id)
        demerit = _demerit_hours(hours_since)
        base = -abs(d_src - med)
        total = base - demerit
        scored.append((total, obs))
    scored.sort(key=lambda x: -x[0])
    top20 = [obs for _, obs in scored[:20]]
    return _deterministic_pick(managed_node, top20, slot or "intra_zone")


def _pick_dx(
    managed_node,
    last_heard_within_hours,
    last_traced_hours,
    managed_node_ids,
    suppressed,
    slot,
    *,
    across: bool,
):
    constellation = managed_node.constellation
    source_pos = managed_node_lat_lon(managed_node)
    if not source_pos:
        return None

    centroid = _centroid_lat_lon(constellation) if constellation else None
    env = get_constellation_envelope(constellation) if constellation else None

    br_src = None
    if centroid:
        br_src = initial_bearing_deg(
            centroid[0],
            centroid[1],
            source_pos[0],
            source_pos[1],
        )

    half_windows = list(range(45, 91, 15))

    strategy_key = "dx_across" if across else "dx_same_side"
    for half_w in half_windows:
        ranked = _dx_candidate_rank(
            managed_node,
            last_heard_within_hours,
            last_traced_hours,
            managed_node_ids,
            suppressed,
            env,
            centroid,
            br_src,
            half_w,
            across=across,
        )
        if ranked:
            return _deterministic_pick(managed_node, ranked[:20], slot or strategy_key)
    return None


def _dx_candidate_rank(
    managed_node,
    last_heard_within_hours,
    last_traced_hours,
    managed_node_ids,
    suppressed,
    env,
    centroid,
    br_src,
    half_window,
    *,
    across,
) -> list[ObservedNode]:
    """Return ObservedNodes sorted best-first for current half_window (periphery + bearing)."""
    source_pos = managed_node_lat_lon(managed_node)
    if not source_pos or br_src is None or centroid is None:
        # Fall back to distant bias only (same base iterator)
        scored = list(
            _iter_scored_candidates(
                managed_node,
                last_heard_within_hours,
                last_traced_hours,
                managed_node_ids,
                suppressed,
            )
        )
        scored.sort(key=lambda x: -x[0])
        return [obs for _, obs in scored[:20]]

    c_lat, c_lon = centroid
    center_bearing = (br_src + 180.0) % 360.0 if across else br_src

    scored = []
    for score, obs in _iter_scored_candidates(
        managed_node,
        last_heard_within_hours,
        last_traced_hours,
        managed_node_ids,
        suppressed,
    ):
        lat = obs.latest_status.latitude
        lon = obs.latest_status.longitude

        if env:
            d_centroid = haversine_km(c_lat, c_lon, lat, lon)
            if d_centroid <= env["radius_km"]:
                continue

        br_t = bearing_from_centroid_to_point(
            env if env else {"centroid_lat": c_lat, "centroid_lon": c_lon},
            lat,
            lon,
        )

        if bearing_difference_deg(br_t, center_bearing) > half_window:
            continue

        scored.append((score, obs))

    if not scored:
        return []

    scored.sort(key=lambda x: -x[0])
    return [obs for _, obs in scored]
