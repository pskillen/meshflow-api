"""
Redis-backed LRU for which **target strategy** to run for a given feeder on the next
auto (or manual) traceroute. Complements :func:`source_selection.select_traceroute_source`
which picks *which* feeder runs; this module picks *which hypothesis* to test.

Works with variable scheduler cadence (e.g. solar-driven) because it is state-based, not
time-of-day keyed.
"""

from __future__ import annotations

from django.core.cache import cache
from django.utils import timezone

from constellations.geometry import (
    get_constellation_envelope,
    is_perimeter_feeder,
    managed_node_position_lat_lon,
)
from nodes.models import ManagedNode

from .models import AutoTraceRoute

KEY_FMT = "tr:strategy:last:{feeder_pk}:{strategy}"
# Long enough to outlast any realistic TR cadence; keys are refreshed on each run
STRATEGY_LRU_TTL_SECONDS = 60 * 60 * 24 * 30

# Tie-break when all strategies are equally "stale" (e.g. cold cache)
STRATEGY_TIE_ORDER = [
    AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE,
    AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS,
    AutoTraceRoute.TARGET_STRATEGY_DX_SAME_SIDE,
]


def applicable_strategies(managed_node: ManagedNode) -> list[str]:
    """
    Perimeter feeder with a defined envelope: intra_zone, dx_across, dx_same_side.
    Internal feeder (or no envelope): dx_across, dx_same_side only.
    """
    if not managed_node.constellation_id:
        return _dx_pair()
    env = get_constellation_envelope(managed_node.constellation)
    if env is None:
        return _dx_pair()
    if is_perimeter_feeder(managed_node, env):
        return [
            AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE,
            AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS,
            AutoTraceRoute.TARGET_STRATEGY_DX_SAME_SIDE,
        ]
    return _dx_pair()


def _dx_pair() -> list[str]:
    return [AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS, AutoTraceRoute.TARGET_STRATEGY_DX_SAME_SIDE]


def _tie_index(strategy: str) -> int:
    try:
        return STRATEGY_TIE_ORDER.index(strategy)
    except ValueError:
        return 99


def _strategy_sort_tuple(strategy: str, last_iso: str | None) -> tuple:
    """Never-run sorts before runs; oldest ISO timestamp next; stable strategy order on ties."""
    ti = _tie_index(strategy)
    if last_iso is None:
        return (0, ti)
    return (1, last_iso, ti)


def ordered_strategies_for_feeder(managed_node: ManagedNode) -> list[str]:
    """
    Applicable strategies for *managed_node* ordered by Redis LRU (stalest first),
    matching :func:`pick_strategy_for_feeder` tie-breaking.
    """
    strategies = applicable_strategies(managed_node)
    if not strategies:
        return []

    keys = [KEY_FMT.format(feeder_pk=managed_node.pk, strategy=s) for s in strategies]
    lasts = cache.get_many(keys)

    decorated: list[tuple[tuple, str]] = []
    for s in strategies:
        k = KEY_FMT.format(feeder_pk=managed_node.pk, strategy=s)
        iso = lasts.get(k)
        decorated.append((_strategy_sort_tuple(s, iso), s))
    decorated.sort(key=lambda x: x[0])
    return [s for _, s in decorated]


def pick_strategy_for_feeder(managed_node: ManagedNode) -> str | None:
    ordered = ordered_strategies_for_feeder(managed_node)
    return ordered[0] if ordered else None


def record_strategy_run(managed_node: ManagedNode, strategy: str | None) -> None:
    """Mark *strategy* as having just run for LRU rotation (manual triggers may participate)."""
    if strategy is None:
        return
    if strategy not in (
        AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE,
        AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS,
        AutoTraceRoute.TARGET_STRATEGY_DX_SAME_SIDE,
    ):
        return

    key = KEY_FMT.format(feeder_pk=managed_node.pk, strategy=strategy)
    cache.set(key, timezone.now().isoformat(), STRATEGY_LRU_TTL_SECONDS)


def feeder_has_position_for_strategies(managed_node: ManagedNode) -> bool:
    """DX strategies need source coordinates; intra_zone also."""
    return managed_node_position_lat_lon(managed_node) is not None
