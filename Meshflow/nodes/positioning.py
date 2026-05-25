"""Resolve geographic position for managed nodes (traceroute, monitoring)."""

from __future__ import annotations

from nodes.models import LocationSource, ManagedNode, ObservedNode


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
