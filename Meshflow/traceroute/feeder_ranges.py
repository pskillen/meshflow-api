"""Compute per-feeder "success range" percentiles from completed traceroutes.

For each ManagedNode (the "feeder"), gather the geographic distance from the
feeder to the target ObservedNode of each successful AutoTraceRoute in a time
window. Return the distribution percentiles (p50/p90/p95/max) and sample count.

Two partitions are returned per feeder:

- ``direct``: only TRs where both ``route`` and ``route_back`` are empty (RF
  reach without repeaters). This is what most operators mean by "my radio's
  range".
- ``any``: every completed TR, including those that hopped via relays. A measure
  of mesh connectivity rather than raw RF reach.

See ``docs/features/traceroute/feeder_ranges.md`` for the full metric
definition and caveats.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from django.db.models import Q

from common.geo import haversine_km
from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import ManagedNode, NodeLatestStatus, ObservedNode

from .models import AutoTraceRoute

DEFAULT_MIN_SAMPLES = 10


@dataclass(frozen=True)
class _FeederMeta:
    managed_node_id: str
    node_id: int
    node_id_str: str
    short_name: str | None
    long_name: str | None
    lat: float
    lng: float


def _percentile(values: list[float], p: float) -> float:
    """Return the ``p``-th percentile (0-100) of ``values`` using linear interpolation.

    For a single value the percentile is the value itself; for two values we fall
    back to linear interpolation between them. ``values`` is assumed to be
    non-empty.
    """
    if not values:
        raise ValueError("values must be non-empty")
    n = len(values)
    if n == 1:
        return float(values[0])
    sorted_vals = sorted(values)
    rank = (p / 100.0) * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def _summarise(distances: list[float], min_samples: int) -> dict:
    sample_count = len(distances)
    if sample_count == 0:
        return {
            "sample_count": 0,
            "p50_km": None,
            "p90_km": None,
            "p95_km": None,
            "max_km": None,
            "low_confidence": True,
        }
    return {
        "sample_count": sample_count,
        "p50_km": round(_percentile(distances, 50), 3),
        "p90_km": round(_percentile(distances, 90), 3),
        "p95_km": round(_percentile(distances, 95), 3),
        "max_km": round(max(distances), 3),
        "low_confidence": sample_count < min_samples,
    }


def _is_direct(tr: AutoTraceRoute) -> bool:
    """A traceroute is direct if neither leg involved any relay."""
    return not (tr.route or []) and not (tr.route_back or [])


def _bulk_target_positions(target_internal_ids: Iterable) -> dict:
    """Return ``{observed_internal_id: (lat, lon)}`` for targets that have a position."""
    statuses = NodeLatestStatus.objects.filter(
        node__internal_id__in=list(target_internal_ids),
        latitude__isnull=False,
        longitude__isnull=False,
    ).values("node_id", "latitude", "longitude")
    # ``node_id`` here is the FK column to ObservedNode (its UUID PK), not the meshtastic node id.
    return {row["node_id"]: (row["latitude"], row["longitude"]) for row in statuses}


def _bulk_feeder_positions(feeders: list[ManagedNode]) -> dict:
    """Return ``{managed_internal_id: (lat, lon)}`` for feeders that resolve to a position.

    Tries ``default_location_*`` first, then falls back to the linked ObservedNode
    via a single bulk query.
    """
    positions: dict = {}
    needs_observed: list[ManagedNode] = []
    for mn in feeders:
        if mn.default_location_latitude is not None and mn.default_location_longitude is not None:
            positions[mn.internal_id] = (
                mn.default_location_latitude,
                mn.default_location_longitude,
            )
        else:
            needs_observed.append(mn)

    if needs_observed:
        node_ids = {mn.node_id for mn in needs_observed}
        observed_pos = {
            row["node_id"]: (row["latest_status__latitude"], row["latest_status__longitude"])
            for row in ObservedNode.objects.filter(
                node_id__in=node_ids,
                latest_status__latitude__isnull=False,
                latest_status__longitude__isnull=False,
            ).values("node_id", "latest_status__latitude", "latest_status__longitude")
        }
        for mn in needs_observed:
            pos = observed_pos.get(mn.node_id)
            if pos is not None:
                positions[mn.internal_id] = pos
    return positions


def compute_feeder_ranges(
    *,
    triggered_at_after: datetime | None = None,
    triggered_at_before: datetime | None = None,
    constellation_id: int | None = None,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> dict:
    """Compute per-feeder distance distributions for completed traceroutes.

    Returns a dict shaped like::

        {
            "feeders": [{...}, ...],
            "meta": {
                "min_samples": int,
                "window": {"start": iso|None, "end": iso|None},
            },
        }
    """
    qs = AutoTraceRoute.objects.filter(status=AutoTraceRoute.STATUS_COMPLETED).select_related(
        "source_node", "target_node"
    )
    if triggered_at_after is not None:
        qs = qs.filter(triggered_at__gte=triggered_at_after)
    if triggered_at_before is not None:
        qs = qs.filter(triggered_at__lte=triggered_at_before)
    if constellation_id is not None:
        qs = qs.filter(source_node__constellation_id=constellation_id)
    qs = qs.filter(Q(source_node__isnull=False) & Q(target_node__isnull=False))

    rows = list(qs.only("source_node", "target_node", "route", "route_back"))
    if not rows:
        return {
            "feeders": [],
            "meta": {
                "min_samples": min_samples,
                "window": {
                    "start": triggered_at_after.isoformat() if triggered_at_after else None,
                    "end": triggered_at_before.isoformat() if triggered_at_before else None,
                },
            },
        }

    # Bulk position lookups: feeders + targets
    feeder_internal_ids = {r.source_node_id for r in rows}
    feeders = list(ManagedNode.objects.filter(internal_id__in=feeder_internal_ids).select_related("constellation"))
    feeder_positions = _bulk_feeder_positions(feeders)

    target_internal_ids = {r.target_node_id for r in rows}
    target_positions = _bulk_target_positions(target_internal_ids)

    # Bulk-fetch observed-node display fields by mesh node_id (for short/long_name on feeders).
    feeder_node_ids = {mn.node_id for mn in feeders}
    observed_display = {
        row["node_id"]: row
        for row in ObservedNode.objects.filter(node_id__in=feeder_node_ids).values("node_id", "short_name", "long_name")
    }

    feeder_meta_by_internal: dict = {}
    for mn in feeders:
        pos = feeder_positions.get(mn.internal_id)
        if pos is None:
            continue
        display = observed_display.get(mn.node_id) or {}
        feeder_meta_by_internal[mn.internal_id] = _FeederMeta(
            managed_node_id=str(mn.internal_id),
            node_id=mn.node_id,
            node_id_str=meshtastic_id_to_hex(mn.node_id),
            short_name=display.get("short_name") or mn.name,
            long_name=display.get("long_name"),
            lat=pos[0],
            lng=pos[1],
        )

    # Walk rows once, distribute distances into direct / any per feeder.
    distances_direct: dict = {fid: [] for fid in feeder_meta_by_internal}
    distances_any: dict = {fid: [] for fid in feeder_meta_by_internal}

    for tr in rows:
        feeder = feeder_meta_by_internal.get(tr.source_node_id)
        if feeder is None:
            continue
        target_pos = target_positions.get(tr.target_node_id)
        if target_pos is None:
            continue
        dist = haversine_km(feeder.lat, feeder.lng, target_pos[0], target_pos[1])
        distances_any[tr.source_node_id].append(dist)
        if _is_direct(tr):
            distances_direct[tr.source_node_id].append(dist)

    feeders_out: list = []
    for internal_id, meta in feeder_meta_by_internal.items():
        any_distances = distances_any[internal_id]
        if not any_distances:
            continue
        feeders_out.append(
            {
                "managed_node_id": meta.managed_node_id,
                "node_id": meta.node_id,
                "node_id_str": meta.node_id_str,
                "short_name": meta.short_name,
                "long_name": meta.long_name,
                "lat": meta.lat,
                "lng": meta.lng,
                "direct": _summarise(distances_direct[internal_id], min_samples),
                "any": _summarise(any_distances, min_samples),
            }
        )
    feeders_out.sort(key=lambda f: f["node_id_str"])

    return {
        "feeders": feeders_out,
        "meta": {
            "min_samples": min_samples,
            "window": {
                "start": triggered_at_after.isoformat() if triggered_at_after else None,
                "end": triggered_at_before.isoformat() if triggered_at_before else None,
            },
        },
    }
