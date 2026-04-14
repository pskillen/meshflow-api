"""Backward-compatible re-exports; canonical implementation in nodes.managed_node_liveness."""

from nodes.managed_node_liveness import (
    DEFAULT_SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS,
    eligible_auto_traceroute_sources_queryset,
    is_managed_node_eligible_traceroute_source,
    schedule_traceroute_source_recency_seconds,
)

__all__ = [
    "DEFAULT_SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS",
    "eligible_auto_traceroute_sources_queryset",
    "is_managed_node_eligible_traceroute_source",
    "schedule_traceroute_source_recency_seconds",
]
