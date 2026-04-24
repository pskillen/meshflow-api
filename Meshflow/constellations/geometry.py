"""Constellation geography: centroid, circular envelope (p90 radius), bearings."""

from __future__ import annotations

import math
import os
from typing import Any

from django.core.cache import cache

from common.geo import haversine_km
from nodes.models import ManagedNode, ObservedNode

ENVELOPE_CACHE_PREFIX = "tr:envelope:v2"
ENVELOPE_TTL_SECONDS = 600

# Source farther than this fraction of envelope radius counts as "perimeter" feeder
PERIMETER_DISTANCE_FRACTION = float(os.environ.get("TR_PERIMETER_THRESHOLD", "0.6"))

OCTANTS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Forward azimuth from (lat1,lon1) to (lat2,lon2), degrees 0–360 (0 = north)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360) % 360


def bearing_difference_deg(a: float, b: float) -> float:
    """Smallest angle between two compass bearings in degrees (0–180)."""
    d = abs((a - b + 540) % 360 - 180)
    return d


def octant_from_bearing(deg: float) -> str:
    x = (deg + 22.5) % 360
    return OCTANTS[int(x // 45) % 8]


def managed_node_position_lat_lon(managed_node: ManagedNode) -> tuple[float, float] | None:
    """Prefer configured default location; else ObservedNode latest_status coordinates."""
    if managed_node.default_location_latitude is not None and managed_node.default_location_longitude is not None:
        return (managed_node.default_location_latitude, managed_node.default_location_longitude)
    try:
        obs = ObservedNode.objects.select_related("latest_status").get(node_id=managed_node.node_id)
    except ObservedNode.DoesNotExist:
        return None
    st = obs.latest_status
    if st is None or st.latitude is None or st.longitude is None:
        return None
    return (st.latitude, st.longitude)


def constellation_centroid(constellation) -> tuple[float, float] | None:
    """Mean of positions for managed nodes that are actively feeding (ManagedNodeStatus)."""
    positions: list[tuple[float, float]] = []
    for mn in ManagedNode.objects.filter(constellation=constellation, status__is_sending_data=True).iterator():
        p = managed_node_position_lat_lon(mn)
        if p:
            positions.append(p)
    if not positions:
        return None
    return (
        sum(p[0] for p in positions) / len(positions),
        sum(p[1] for p in positions) / len(positions),
    )


def _compute_envelope_circle(constellation) -> dict[str, Any] | None:
    """
    Circular envelope: centroid + p90 distance from centroid to managed-node positions
    for nodes that are actively feeding (ManagedNodeStatus.is_sending_data).

    Returns ``None`` when fewer than three managed nodes have coordinates (undefined).
    """
    positions: list[tuple[float, float]] = []
    for mn in ManagedNode.objects.filter(constellation=constellation, status__is_sending_data=True).iterator():
        p = managed_node_position_lat_lon(mn)
        if p:
            positions.append(p)

    n = len(positions)
    if n < 3:
        return None

    c_lat = sum(p[0] for p in positions) / n
    c_lon = sum(p[1] for p in positions) / n

    dists_km = sorted(haversine_km(c_lat, c_lon, lat, lon) for lat, lon in positions)
    idx = max(0, min(len(dists_km) - 1, int(math.ceil(0.9 * len(dists_km)) - 1)))
    radius_km = dists_km[idx]
    if radius_km <= 0:
        return None

    return {
        "centroid_lat": c_lat,
        "centroid_lon": c_lon,
        "radius_km": radius_km,
        "n_managed_positions": n,
    }


def get_constellation_envelope(constellation) -> dict[str, Any] | None:
    """Cached envelope (~10 min). Safe to evict — recompute from current managed positions."""
    if constellation is None:
        return None
    key = f"{ENVELOPE_CACHE_PREFIX}:{constellation.pk}"
    val = cache.get(key)
    if val is not None:
        return val
    val = _compute_envelope_circle(constellation)
    cache.set(key, val, ENVELOPE_TTL_SECONDS)
    return val


def is_perimeter_feeder(managed_node: ManagedNode, envelope: dict[str, Any] | None) -> bool:
    """
    A feeder is "perimeter" if it lies at least ``PERIMETER_DISTANCE_FRACTION`` of the
    envelope radius away from the constellation centroid.

    When ``envelope`` is ``None`` (undefined), every feeder is treated as perimeter for
    tier display, but callers should not offer ``intra_zone`` (no envelope).
    """
    if envelope is None:
        return True
    pos = managed_node_position_lat_lon(managed_node)
    if not pos:
        return True
    d_km = haversine_km(pos[0], pos[1], envelope["centroid_lat"], envelope["centroid_lon"])
    return d_km >= PERIMETER_DISTANCE_FRACTION * envelope["radius_km"]


def feeder_tier(managed_node: ManagedNode, envelope: dict[str, Any] | None) -> str:
    """``perimeter`` or ``internal`` (undefined envelope => perimeter for display)."""
    if envelope is None:
        return "perimeter"
    return "perimeter" if is_perimeter_feeder(managed_node, envelope) else "internal"


def bearing_from_centroid_to_point(
    envelope: dict[str, Any],
    point_lat: float,
    point_lon: float,
) -> float:
    """Compass bearing from constellation centroid toward the point."""
    return initial_bearing_deg(
        envelope["centroid_lat"],
        envelope["centroid_lon"],
        point_lat,
        point_lon,
    )
