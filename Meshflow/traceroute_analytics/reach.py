"""Compute per-(feeder, target) reliability rows for the coverage map.

For every ManagedNode (the "feeder") and every ObservedNode it has attempted
a traceroute to in a window, return the count of attempts and successes. This
is the shared substrate behind both coverage endpoints:

- ``feeder_reach`` returns the per-target rows directly, so the frontend can
  render dots, client-side H3 hexagons, and a concave-hull polygon off one
  fetch.
- ``constellation_coverage`` H3-bins these rows on the server.

A successful row is ``status = COMPLETED``; a failed row is ``status = FAILED``.
Rows still pending or sent are excluded entirely (we don't know yet whether
they'll succeed). Targets without a known position are dropped.

See ``docs/features/traceroute/coverage.md`` for the full data definition and
caveats (no position-freshness filter, constellation-membership not enforced
in the auth layer, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from django.db.models import Count, Q

from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import ManagedNode, NodeLatestStatus, ObservedNode
from traceroute.models import AutoTraceRoute


def target_strategy_tokens_to_q(tokens: Iterable[str]) -> Q | None:
    """Build an OR filter over ``AutoTraceRoute.target_strategy`` for CSV tokens.

    ``legacy`` matches null or explicit legacy strategy, matching traceroute list
    behaviour.
    """
    strat_q = Q()
    any_valid = False
    for t in tokens:
        if t in ("legacy", AutoTraceRoute.TARGET_STRATEGY_LEGACY):
            strat_q |= Q(target_strategy__isnull=True) | Q(target_strategy=AutoTraceRoute.TARGET_STRATEGY_LEGACY)
            any_valid = True
        elif t in dict(AutoTraceRoute.TARGET_STRATEGY_CHOICES):
            strat_q |= Q(target_strategy=t)
            any_valid = True
    return strat_q if any_valid else None


@dataclass(frozen=True)
class ReachRow:
    """One (feeder, target) pair with attempt and success counts in window."""

    feeder_managed_node_id: str
    feeder_node_id: int
    feeder_node_id_str: str
    feeder_short_name: str | None
    feeder_long_name: str | None
    feeder_lat: float
    feeder_lng: float

    target_node_id: int
    target_node_id_str: str
    target_short_name: str | None
    target_long_name: str | None
    target_lat: float
    target_lng: float

    attempts: int
    successes: int


def _bulk_target_positions_by_node_id(target_internal_ids: Iterable) -> dict:
    """Return ``{observed_internal_id: (lat, lon, node_id, short, long)}``.

    Pulls the position from ``NodeLatestStatus`` and the display fields from
    the linked ``ObservedNode`` in one query. Targets without a non-null lat/lng
    are excluded.
    """
    rows = NodeLatestStatus.objects.filter(
        node__internal_id__in=list(target_internal_ids),
        latitude__isnull=False,
        longitude__isnull=False,
    ).values(
        "node_id",
        "latitude",
        "longitude",
        "node__node_id",
        "node__short_name",
        "node__long_name",
    )
    return {
        r["node_id"]: (
            r["latitude"],
            r["longitude"],
            r["node__node_id"],
            r["node__short_name"],
            r["node__long_name"],
        )
        for r in rows
    }


def _bulk_feeder_positions(feeders: list[ManagedNode]) -> dict:
    """Return ``{managed_internal_id: (lat, lon)}`` for feeders that resolve to a position.

    Tries ``default_location_*`` first, then falls back to the linked
    ``ObservedNode`` via a single bulk query.
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


def compute_reach(
    *,
    triggered_at_after: datetime | None = None,
    triggered_at_before: datetime | None = None,
    constellation_id: int | None = None,
    feeder_id: int | None = None,
    target_strategy_tokens: list[str] | None = None,
) -> list[ReachRow]:
    """Aggregate per-(feeder, target) attempt and success counts.

    ``feeder_id`` is the meshtastic node id of a ManagedNode (not the internal
    UUID) so callers can use the same id space as the rest of the API.

    ``target_strategy_tokens`` optionally restricts to traceroutes whose
    ``target_strategy`` matches one of the tokens (``legacy`` matches null or
    explicit legacy).

    Rows where the target has no known position are dropped. Rows where the
    feeder has no known position are dropped. Pending and sent traceroutes are
    excluded; only COMPLETED and FAILED rows count toward ``attempts``.
    """
    qs = AutoTraceRoute.objects.filter(
        status__in=[AutoTraceRoute.STATUS_COMPLETED, AutoTraceRoute.STATUS_FAILED],
    )
    if triggered_at_after is not None:
        qs = qs.filter(triggered_at__gte=triggered_at_after)
    if triggered_at_before is not None:
        qs = qs.filter(triggered_at__lte=triggered_at_before)
    if constellation_id is not None:
        qs = qs.filter(source_node__constellation_id=constellation_id)
    if feeder_id is not None:
        qs = qs.filter(source_node__node_id=feeder_id)
    qs = qs.filter(source_node__isnull=False, target_node__isnull=False)

    if target_strategy_tokens:
        fq = target_strategy_tokens_to_q(target_strategy_tokens)
        if fq is not None:
            qs = qs.filter(fq)

    grouped = list(
        qs.values("source_node_id", "target_node_id").annotate(
            attempts=Count("id"),
            successes=Count("id", filter=Q(status=AutoTraceRoute.STATUS_COMPLETED)),
        )
    )
    if not grouped:
        return []

    feeder_internal_ids = {g["source_node_id"] for g in grouped}
    target_internal_ids = {g["target_node_id"] for g in grouped}

    feeders = list(ManagedNode.objects.filter(internal_id__in=feeder_internal_ids, deleted_at__isnull=True))
    feeder_positions = _bulk_feeder_positions(feeders)

    feeder_node_ids = {mn.node_id for mn in feeders}
    feeder_display = {
        row["node_id"]: row
        for row in ObservedNode.objects.filter(node_id__in=feeder_node_ids).values("node_id", "short_name", "long_name")
    }

    feeder_meta_by_internal: dict = {}
    for mn in feeders:
        pos = feeder_positions.get(mn.internal_id)
        if pos is None:
            continue
        display = feeder_display.get(mn.node_id) or {}
        feeder_meta_by_internal[mn.internal_id] = {
            "managed_node_id": str(mn.internal_id),
            "node_id": mn.node_id,
            "node_id_str": meshtastic_id_to_hex(mn.node_id),
            "short_name": display.get("short_name") or mn.name,
            "long_name": display.get("long_name"),
            "lat": pos[0],
            "lng": pos[1],
        }

    target_positions = _bulk_target_positions_by_node_id(target_internal_ids)

    out: list[ReachRow] = []
    for g in grouped:
        feeder_meta = feeder_meta_by_internal.get(g["source_node_id"])
        if feeder_meta is None:
            continue
        target = target_positions.get(g["target_node_id"])
        if target is None:
            continue
        target_lat, target_lng, target_node_id, target_short, target_long = target
        out.append(
            ReachRow(
                feeder_managed_node_id=feeder_meta["managed_node_id"],
                feeder_node_id=feeder_meta["node_id"],
                feeder_node_id_str=feeder_meta["node_id_str"],
                feeder_short_name=feeder_meta["short_name"],
                feeder_long_name=feeder_meta["long_name"],
                feeder_lat=feeder_meta["lat"],
                feeder_lng=feeder_meta["lng"],
                target_node_id=target_node_id,
                target_node_id_str=meshtastic_id_to_hex(target_node_id),
                target_short_name=target_short,
                target_long_name=target_long,
                target_lat=target_lat,
                target_lng=target_lng,
                attempts=g["attempts"],
                successes=g["successes"],
            )
        )
    return out


def aggregate_reach_rows_to_constellation_targets(rows: list[ReachRow]) -> list[dict]:
    """Merge per-(feeder, target) rows into one dict per target for constellation maps."""
    by_target: dict[int, dict] = {}
    for r in rows:
        tid = r.target_node_id
        if tid not in by_target:
            by_target[tid] = {
                "node_id": tid,
                "node_id_str": r.target_node_id_str,
                "short_name": r.target_short_name,
                "long_name": r.target_long_name,
                "lat": r.target_lat,
                "lng": r.target_lng,
                "attempts": 0,
                "successes": 0,
                "feeder_node_ids": set(),
            }
        agg = by_target[tid]
        agg["attempts"] += r.attempts
        agg["successes"] += r.successes
        agg["feeder_node_ids"].add(r.feeder_node_id)

    targets = []
    for agg in by_target.values():
        feeder_ids = agg.pop("feeder_node_ids")
        targets.append({**agg, "contributing_feeders": len(feeder_ids)})
    targets.sort(key=lambda t: t["node_id"])
    return targets


def constellation_feeder_markers(constellation_id: int) -> list[dict]:
    """All managed nodes in a constellation with a resolvable map position."""
    feeders = list(ManagedNode.objects.filter(constellation_id=constellation_id, deleted_at__isnull=True))
    if not feeders:
        return []

    positions = _bulk_feeder_positions(feeders)
    node_ids = {mn.node_id for mn in feeders}
    feeder_display = {
        row["node_id"]: row
        for row in ObservedNode.objects.filter(node_id__in=node_ids).values("node_id", "short_name", "long_name")
    }

    out: list[dict] = []
    for mn in feeders:
        pos = positions.get(mn.internal_id)
        if pos is None:
            continue
        display = feeder_display.get(mn.node_id) or {}
        out.append(
            {
                "managed_node_id": str(mn.internal_id),
                "node_id": mn.node_id,
                "node_id_str": meshtastic_id_to_hex(mn.node_id),
                "short_name": display.get("short_name") or mn.name,
                "long_name": display.get("long_name"),
                "lat": pos[0],
                "lng": pos[1],
            }
        )
    out.sort(key=lambda x: x["node_id"])
    return out
