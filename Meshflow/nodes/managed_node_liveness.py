"""Managed-node eligibility based on recent packet ingestion (traceroute sources, monitoring)."""

import os

from nodes.models import ManagedNode

DEFAULT_SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS = 600


def schedule_traceroute_source_recency_seconds() -> int:
    """Max age (seconds) of last packet ingestion for a source to be schedulable."""
    raw = os.environ.get(
        "SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS",
        str(DEFAULT_SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS),
    )
    return int(raw)


def eligible_auto_traceroute_sources_queryset():
    """
    ManagedNodes that may run auto traceroutes: allow_auto_traceroute and denormalized
    ManagedNodeStatus.is_sending_data (refreshed periodically; same recency window as
    schedule_traceroute_source_recency_seconds in nodes.tasks.update_managed_node_statuses).
    """
    return ManagedNode.objects.filter(
        deleted_at__isnull=True,
        allow_auto_traceroute=True,
        status__is_sending_data=True,
    ).select_related("constellation", "status")


def is_managed_node_eligible_traceroute_source(managed_node: ManagedNode) -> bool:
    """True if this managed node may be used as a traceroute source (scheduler or API trigger)."""
    return eligible_auto_traceroute_sources_queryset().filter(pk=managed_node.pk).exists()
