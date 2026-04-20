"""Per-feeder geo tier + strategy hints for API ``include=geo_classification``."""

from __future__ import annotations

from constellations.geometry import (
    constellation_centroid,
    feeder_tier,
    get_constellation_envelope,
    initial_bearing_deg,
    managed_node_position_lat_lon,
    octant_from_bearing,
)
from nodes.models import ManagedNode

from .strategy_rotation import applicable_strategies


def build_geo_classification(managed_node: ManagedNode) -> dict:
    """
    Return ``tier`` (perimeter/internal), ``bearing_octant`` (optional), and
    ``applicable_strategies`` for trigger UI.
    """
    constellation = managed_node.constellation
    env = get_constellation_envelope(constellation) if constellation else None
    tier = feeder_tier(managed_node, env)

    pos = managed_node_position_lat_lon(managed_node)
    octant: str | None = None
    if pos and env:
        br = initial_bearing_deg(
            env["centroid_lat"],
            env["centroid_lon"],
            pos[0],
            pos[1],
        )
        octant = octant_from_bearing(br)
    elif pos and constellation is not None:
        c = constellation_centroid(constellation)
        if c:
            br = initial_bearing_deg(c[0], c[1], pos[0], pos[1])
            octant = octant_from_bearing(br)

    return {
        "tier": tier,
        "bearing_octant": octant,
        "applicable_strategies": applicable_strategies(managed_node),
    }
