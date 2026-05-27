"""Map position helpers for message heard UI."""

from __future__ import annotations

from common.protocol import Protocol
from nodes.models import ManagedNode, ObservedNode
from nodes.positioning import managed_node_lat_lon, observed_node_lat_lon


def map_position_dict(latitude, longitude) -> dict | None:
    if latitude is None or longitude is None:
        return None
    return {"latitude": float(latitude), "longitude": float(longitude)}


def observed_node_map_position(node: ObservedNode | None) -> dict | None:
    if node is None:
        return None
    coords = observed_node_lat_lon(node)
    if coords:
        return map_position_dict(coords[0], coords[1])
    return None


def managed_node_map_position(managed_node: ManagedNode) -> dict | None:
    if managed_node.default_location_latitude is not None and managed_node.default_location_longitude is not None:
        return map_position_dict(
            managed_node.default_location_latitude,
            managed_node.default_location_longitude,
        )
    if managed_node.protocol == Protocol.MESHCORE and managed_node.mc_pubkey:
        obs = (
            ObservedNode.objects.filter(protocol=Protocol.MESHCORE, mc_pubkey=managed_node.mc_pubkey.lower())
            .select_related("latest_status")
            .first()
        )
        pos = observed_node_map_position(obs)
        if pos:
            return pos
    coords = managed_node_lat_lon(managed_node)
    if coords:
        return map_position_dict(coords[0], coords[1])
    return None
