"""
Pluggable auto-traceroute **source** selection (which ManagedNode runs the cycle).

Algorithms are **stateless** aside from reading ``AutoTraceRoute`` history via the ORM.

Deferred / future selectors (documented here and in meshflow-api#178):

- ``round_robin`` — deterministic cursor; requires persisted state; manual triggers do
  not participate naturally in fairness unless extended.
- ``coverage_aware`` — lowest TR count in last N hours per constellation bucket.
- ``weighted_recency`` — probabilistic LRU.
- ``epsilon_greedy_lru`` — explore vs exploit mix.
- ``success_aware`` / ``failure_aware`` — weight by recent TR outcomes.
- ``priority_weighted`` — model field on ManagedNode for operator overrides.

See also: ``AUTO_TR_SOURCE_SELECTION_ALGO`` env var.
"""

from __future__ import annotations

import logging
import os
import random

from django.db.models import F, Max

from nodes.models import ManagedNode

from .source_eligibility import eligible_auto_traceroute_sources_queryset

logger = logging.getLogger(__name__)

DEFAULT_ALGO = "least_recently_used"


def _select_random(qs):
    nodes = list(qs)
    return random.choice(nodes) if nodes else None


def _select_lru(qs):
    return (
        qs.annotate(last_tr=Max("traceroutes_sent__triggered_at")).order_by(F("last_tr").asc(nulls_first=True)).first()
    )


def _select_stratified_lru(qs):
    """
    Two-level LRU: pick the constellation whose most recent TR (any feeder) is oldest,
    then LRU among feeders in that constellation.
    """
    eligible = list(qs.values_list("pk", flat=True))
    if not eligible:
        return None

    last_per_constellation = (
        ManagedNode.objects.filter(pk__in=eligible)
        .values("constellation_id")
        .annotate(c_last_tr=Max("traceroutes_sent__triggered_at"))
        .order_by(F("c_last_tr").asc(nulls_first=True))
    )
    row = last_per_constellation.first()
    if not row:
        return _select_lru(qs)
    cid = row["constellation_id"]
    return _select_lru(qs.filter(constellation_id=cid))


def select_traceroute_source():
    """
    Pick one eligible ManagedNode to originate the next auto traceroute.

    Env: ``AUTO_TR_SOURCE_SELECTION_ALGO`` — ``least_recently_used`` (default),
    ``random``, or ``stratified_lru``. Unknown values log a warning and fall back to
    the default.
    """
    raw = os.environ.get("AUTO_TR_SOURCE_SELECTION_ALGO", DEFAULT_ALGO)
    name = raw.strip().lower() if raw else DEFAULT_ALGO
    selector = SOURCE_SELECTORS.get(name)
    if selector is None:
        logger.warning(
            "Unknown AUTO_TR_SOURCE_SELECTION_ALGO=%r, falling back to %s",
            name,
            DEFAULT_ALGO,
        )
        selector = SOURCE_SELECTORS[DEFAULT_ALGO]

    qs = eligible_auto_traceroute_sources_queryset()
    chosen = selector(qs)
    if chosen:
        logger.info(
            "select_traceroute_source: algo=%s chose %s",
            name if name in SOURCE_SELECTORS else DEFAULT_ALGO,
            chosen.node_id_str,
        )
    return chosen


SOURCE_SELECTORS = {
    "random": _select_random,
    "least_recently_used": _select_lru,
    "stratified_lru": _select_stratified_lru,
}
