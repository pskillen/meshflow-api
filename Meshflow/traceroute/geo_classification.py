"""Per-feeder geo tier + strategy hints for API ``include=geo_classification``."""

from __future__ import annotations

from constellations.geometry import (
    PERIMETER_DISTANCE_FRACTION,
    constellation_centroid,
    feeder_tier,
    get_constellation_envelope,
    initial_bearing_deg,
    managed_node_position_lat_lon,
    octant_from_bearing,
)
from nodes.models import ManagedNode

from .strategy_rotation import applicable_strategies

# Match ``pick_traceroute_target`` default; exposed to the UI so preview cannot drift.
SELECTOR_LAST_HEARD_WITHIN_HOURS = 3
# Match ``_pick_dx`` half-window sweep in ``target_selection``.
DX_HALF_WINDOW_SWEEP_DEG = list(range(45, 91, 15))


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

    envelope_payload = None
    if env is not None:
        envelope_payload = {
            "centroid_lat": env["centroid_lat"],
            "centroid_lon": env["centroid_lon"],
            "radius_km": env["radius_km"],
        }

    selection_centroid: tuple[float, float] | None = None
    if env is not None:
        selection_centroid = (env["centroid_lat"], env["centroid_lon"])
    elif constellation is not None:
        selection_centroid = constellation_centroid(constellation)

    source_bearing_deg: float | None = None
    if pos:
        if env is not None:
            source_bearing_deg = initial_bearing_deg(
                env["centroid_lat"],
                env["centroid_lon"],
                pos[0],
                pos[1],
            )
        elif constellation is not None:
            c = constellation_centroid(constellation)
            if c:
                source_bearing_deg = initial_bearing_deg(c[0], c[1], pos[0], pos[1])

    selector_params = {
        "last_heard_within_hours": SELECTOR_LAST_HEARD_WITHIN_HOURS,
        "dx_half_window_sweep_deg": DX_HALF_WINDOW_SWEEP_DEG,
        "perimeter_distance_fraction": PERIMETER_DISTANCE_FRACTION,
    }

    centroid_payload = None
    if selection_centroid is not None:
        centroid_payload = {
            "lat": selection_centroid[0],
            "lon": selection_centroid[1],
        }

    return {
        "tier": tier,
        "bearing_octant": octant,
        "applicable_strategies": applicable_strategies(managed_node),
        "envelope": envelope_payload,
        "selection_centroid": centroid_payload,
        "source_bearing_deg": source_bearing_deg,
        "selector_params": selector_params,
    }
