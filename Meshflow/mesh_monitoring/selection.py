"""Pick managed nodes to run monitoring traceroutes toward a target observed node."""

from datetime import timedelta

from django.utils import timezone

from common.geo import haversine_km
from nodes.managed_node_liveness import eligible_auto_traceroute_sources_queryset
from nodes.models import ManagedNode, ObservedNode
from nodes.positioning import managed_node_lat_lon
from traceroute.models import AutoTraceRoute
from traceroute.trigger_intervals import MONITORING_TRIGGER_MIN_INTERVAL_SEC


def observed_node_target_coordinates(observed: ObservedNode) -> tuple[float, float] | None:
    """Lat/lon from latest_status, if present."""
    try:
        st = observed.latest_status
    except ObservedNode.latest_status.RelatedObjectDoesNotExist:
        return None
    if st.latitude is None or st.longitude is None:
        return None
    return (float(st.latitude), float(st.longitude))


def _distance_km(source: ManagedNode, target_lat: float | None, target_lon: float | None) -> float:
    if target_lat is None or target_lon is None:
        return float("inf")
    src = managed_node_lat_lon(source)
    if not src:
        return float("inf")
    return haversine_km(target_lat, target_lon, src[0], src[1])


def _source_ready_for_monitoring_tr(source: ManagedNode, now) -> bool:
    """Respect per-source spacing vs last AutoTraceRoute of any type."""
    cutoff = now - timedelta(seconds=MONITORING_TRIGGER_MIN_INTERVAL_SEC)
    latest = (
        AutoTraceRoute.objects.filter(source_node=source)
        .order_by("-triggered_at")
        .values_list("triggered_at", flat=True)
        .first()
    )
    if latest is None:
        return True
    return latest <= cutoff


def select_monitoring_sources(target: ObservedNode, max_sources: int = 3) -> list[ManagedNode]:
    """
    Up to `max_sources` distinct managed nodes: allow_auto_traceroute, liveness,
    not the target node, not spacing-blocked, closest to target (fallback: stable by node_id).
    """
    now = timezone.now()
    target_pos = observed_node_target_coordinates(target)
    target_lat, target_lon = (target_pos[0], target_pos[1]) if target_pos else (None, None)

    eligible = []
    for mn in eligible_auto_traceroute_sources_queryset():
        if mn.node_id == target.node_id:
            continue
        if not _source_ready_for_monitoring_tr(mn, now):
            continue
        eligible.append(mn)

    eligible.sort(
        key=lambda mn: (
            _distance_km(mn, target_lat, target_lon),
            mn.node_id,
        )
    )

    # Do not pick sources whose only path is "also suppressed as target" — N/A for sources.

    picked = []
    for mn in eligible:
        if len(picked) >= max_sources:
            break
        picked.append(mn)
    return picked
