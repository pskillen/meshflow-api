"""Queue a baseline traceroute when an ObservedNode is first seen (meshflow-api#236)."""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from nodes.managed_node_liveness import is_managed_node_eligible_traceroute_source
from nodes.models import ManagedNode, ObservedNode
from traceroute.dispatch import TRACEROUTE_MAX_PENDING_PER_SOURCE, pending_count_for_source
from traceroute.lifecycle import create_pending_auto_traceroute
from traceroute.models import AutoTraceRoute
from traceroute.source_selection import eligible_traceroute_sources_ordered

logger = logging.getLogger(__name__)

NEW_NODE_BASELINE_TRIGGER_SOURCE = "new_node_observed"

# Returned by :func:`enqueue_new_node_baseline` for metrics and tests.
RESULT_QUEUED = "queued"
RESULT_DUPLICATE = "duplicate"
RESULT_NO_ELIGIBLE_SOURCE = "no_eligible_source"
RESULT_SOURCE_QUEUE_FULL = "source_queue_full"


def _ordered_source_candidates(observer: ManagedNode) -> list[ManagedNode]:
    """Prefer the ingesting observer when eligible, then scheduler-ordered eligible sources."""
    seen: set[int] = set()
    out: list[ManagedNode] = []
    if is_managed_node_eligible_traceroute_source(observer):
        out.append(observer)
        seen.add(observer.pk)
    for node in eligible_traceroute_sources_ordered():
        if node.pk not in seen:
            out.append(node)
            seen.add(node.pk)
    return out


def _pick_source_under_pending_cap(observer: ManagedNode) -> ManagedNode | None:
    for src in _ordered_source_candidates(observer):
        if pending_count_for_source(src.pk) < TRACEROUTE_MAX_PENDING_PER_SOURCE:
            return src
    return None


def enqueue_new_node_baseline(observed_node: ObservedNode, observer: ManagedNode) -> str:
    """
    Create at most one pending AutoTraceRoute per target with trigger NEW_NODE_BASELINE.

    Uses the shared dispatch queue (per-source cap and pacing). Does not send WebSocket
    commands from the request path.
    """
    if AutoTraceRoute.objects.filter(
        target_node_id=observed_node.pk,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE,
    ).exists():
        return RESULT_DUPLICATE

    candidates = _ordered_source_candidates(observer)
    if not candidates:
        logger.info(
            "new_node_baseline: no eligible traceroute sources (target=%s)",
            observed_node.node_id_str,
        )
        return RESULT_NO_ELIGIBLE_SOURCE

    source = _pick_source_under_pending_cap(observer)
    if source is None:
        logger.info(
            "new_node_baseline: all candidate sources at pending cap (target=%s)",
            observed_node.node_id_str,
        )
        return RESULT_SOURCE_QUEUE_FULL

    at_now = timezone.now()
    try:
        with transaction.atomic():
            auto_tr = create_pending_auto_traceroute(
                source_node=source,
                target_node=observed_node,
                trigger_type=AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE,
                triggered_by=None,
                trigger_source=NEW_NODE_BASELINE_TRIGGER_SOURCE,
                target_strategy=None,
                earliest_send_at=at_now,
            )
    except IntegrityError:
        logger.debug(
            "new_node_baseline: race or duplicate constraint (target=%s)",
            observed_node.node_id_str,
            exc_info=True,
        )
        return RESULT_DUPLICATE

    logger.info(
        "new_node_baseline: queued TR id=%s %s -> %s",
        auto_tr.id,
        source.node_id_str,
        observed_node.node_id_str,
    )
    return RESULT_QUEUED
