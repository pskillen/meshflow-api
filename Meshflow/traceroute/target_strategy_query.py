"""Shared Q filters for ``AutoTraceRoute.target_strategy`` (list + analytics)."""

from __future__ import annotations

from typing import Iterable

from django.db.models import Q

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
