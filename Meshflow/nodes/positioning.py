"""Resolve geographic position for managed nodes (traceroute, monitoring)."""

from __future__ import annotations

from typing import Iterable

from django.core.exceptions import ObjectDoesNotExist

from nodes.models import LocationSource, ManagedNode, ObservedNode, Position


def managed_node_default_position_data(managed_node: ManagedNode) -> dict | None:
    """Position dict for API when no observed telemetry; uses operator-configured default location."""
    lat = managed_node.default_location_latitude
    lon = managed_node.default_location_longitude
    if lat is None or lon is None:
        return None
    return {
        "latitude": lat,
        "longitude": lon,
        "altitude": None,
        "reported_time": None,
        "logged_time": None,
        "heading": None,
        "meshtastic_location_source": LocationSource.MANUAL,
        "meshtastic_precision_bits": None,
        "ground_speed": None,
        "ground_track": None,
        "sats_in_view": None,
        "pdop": None,
    }


def observed_node_lat_lon(node: ObservedNode) -> tuple[float, float] | None:
    """
    Lat/lon for map display — same sources as ObservedNode ``latest_position`` API field.

    Prefer ``NodeLatestStatus``; fall back to the newest ``Position`` row when status
    is missing or has no coordinates (common for MeshCore ADVERT history).
    """
    prefetched = getattr(node, "_map_latest_position", None)
    if prefetched is not None:
        if prefetched.latitude is not None and prefetched.longitude is not None:
            return float(prefetched.latitude), float(prefetched.longitude)
        return None

    try:
        status = node.latest_status
    except ObjectDoesNotExist:
        status = None
    if status is not None and status.latitude is not None and status.longitude is not None:
        return float(status.latitude), float(status.longitude)

    position = Position.objects.filter(node=node).order_by("-reported_time").only("latitude", "longitude").first()
    if position is not None and position.latitude is not None and position.longitude is not None:
        return float(position.latitude), float(position.longitude)
    return None


def prefetch_observed_node_positions(nodes: Iterable[ObservedNode]) -> None:
    """Attach ``_map_latest_position`` on each node to avoid N+1 Position lookups."""
    node_list = list(nodes)
    if not node_list:
        return
    node_ids = [node.internal_id for node in node_list]
    latest_by_node: dict = {}
    for position in Position.objects.filter(node_id__in=node_ids).order_by("-reported_time"):
        if position.node_id not in latest_by_node:
            latest_by_node[position.node_id] = position
    for node in node_list:
        node._map_latest_position = latest_by_node.get(node.internal_id)


def managed_node_lat_lon(managed_node: ManagedNode) -> tuple[float, float] | None:
    """Return (lat, lon) for a ManagedNode: default_location or from linked ObservedNode."""
    if managed_node.default_location_latitude is not None and managed_node.default_location_longitude is not None:
        return (
            managed_node.default_location_latitude,
            managed_node.default_location_longitude,
        )
    obs = (
        ObservedNode.objects.filter(meshtastic_node_id=managed_node.meshtastic_node_id)
        .select_related("latest_status")
        .first()
    )
    if obs and obs.latest_status and obs.latest_status.latitude is not None:
        return obs.latest_status.latitude, obs.latest_status.longitude
    return None
