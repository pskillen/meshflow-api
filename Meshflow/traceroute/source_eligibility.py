"""Eligibility rules for auto-scheduled traceroute sources."""

import os
from datetime import timedelta

from django.db.models import Exists, OuterRef
from django.utils import timezone

from nodes.models import ManagedNode
from packets.models import PacketObservation

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
    ManagedNodes that may run auto traceroutes: allow_auto_traceroute and at least one
    PacketObservation as observer with upload_time within the recency window.
    """
    cutoff = timezone.now() - timedelta(seconds=schedule_traceroute_source_recency_seconds())
    recent_observation = PacketObservation.objects.filter(
        observer_id=OuterRef("pk"),
        upload_time__gte=cutoff,
    )
    return (
        ManagedNode.objects.filter(allow_auto_traceroute=True)
        .annotate(_has_recent_ingestion=Exists(recent_observation))
        .filter(_has_recent_ingestion=True)
        .select_related("constellation")
    )


def is_managed_node_eligible_traceroute_source(managed_node: ManagedNode) -> bool:
    """True if this managed node may be used as a traceroute source (scheduler or API trigger)."""
    return eligible_auto_traceroute_sources_queryset().filter(pk=managed_node.pk).exists()
