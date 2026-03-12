"""Target selection for traceroutes (auto mode)."""

import math
from datetime import timedelta

from django.utils import timezone

from nodes.models import ManagedNode, ObservedNode


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


def pick_traceroute_target(
    managed_node: ManagedNode,
    last_heard_within_hours: int = 3,
    slot: str | None = None,
) -> ObservedNode | None:
    """
    Pick one target ObservedNode for a ManagedNode using geography-aware algorithm.

    - Filter: last_heard within N hours, has latest_status with lat/lon
    - Exclude: source node (self), other ManagedNodes
    - Sort by distance descending (prioritise periphery)
    - Take top 20, deterministic choice: hash(managed_node_id + date + slot) % 20
    """
    source_pos = _get_source_position(managed_node)
    if not source_pos:
        return None

    cutoff = timezone.now() - timedelta(hours=last_heard_within_hours)
    managed_node_ids = set(ManagedNode.objects.values_list("node_id", flat=True))

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

    with_dist = []
    for obs in candidates:
        lat = obs.latest_status.latitude
        lon = obs.latest_status.longitude
        dist = _haversine_km(source_pos[0], source_pos[1], lat, lon)
        with_dist.append((dist, obs))

    with_dist.sort(key=lambda x: -x[0])  # descending (periphery first)
    top20 = [obs for _, obs in with_dist[:20]]
    if not top20:
        return None

    date_str = timezone.now().date().isoformat()
    slot_str = slot or "default"
    h = hash((managed_node.node_id, date_str, slot_str)) % (1 << 32)
    idx = h % len(top20)
    return top20[idx]
