"""Resolve geographic position for managed nodes (traceroute, monitoring)."""

from __future__ import annotations

from nodes.models import ManagedNode, ObservedNode


def managed_node_lat_lon(managed_node: ManagedNode) -> tuple[float, float] | None:
    """Return (lat, lon) for a ManagedNode: default_location or from linked ObservedNode."""
    if managed_node.default_location_latitude is not None and managed_node.default_location_longitude is not None:
        return (
            managed_node.default_location_latitude,
            managed_node.default_location_longitude,
        )
    obs = ObservedNode.objects.filter(node_id=managed_node.node_id).select_related("latest_status").first()
    if obs and obs.latest_status and obs.latest_status.latitude is not None:
        return obs.latest_status.latitude, obs.latest_status.longitude
    return None
