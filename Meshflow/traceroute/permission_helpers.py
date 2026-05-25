"""Shared permission logic for traceroute triggering."""

from django.db.models import OuterRef, Subquery

from common.access import user_is_feeder_or_admin
from nodes.models import ManagedNode, NodeLatestStatus, ObservedNode

from .source_eligibility import eligible_auto_traceroute_sources_queryset


def user_can_trigger_from_node(user, source_node):
    """Feeder or admin may trigger from any eligible managed node."""
    if not user_is_feeder_or_admin(user):
        return False
    return source_node.allow_auto_traceroute and source_node.deleted_at is None


def get_nodes_permitted_for_trigger_queryset(user):
    """
    ManagedNodes the user may attempt to trigger from (allow_auto_traceroute),
    without requiring recent ingestion.
    """
    if not user_is_feeder_or_admin(user):
        return ManagedNode.objects.none()
    return ManagedNode.objects.filter(deleted_at__isnull=True, allow_auto_traceroute=True).select_related(
        "constellation"
    )


def get_triggerable_nodes_queryset(user):
    """
    ManagedNodes the user can trigger traceroutes from right now: eligible sources
    and feeder/admin permission.
    """
    if not user_is_feeder_or_admin(user):
        return ManagedNode.objects.none()
    eligible = eligible_auto_traceroute_sources_queryset()
    obs_short = ObservedNode.objects.filter(meshtastic_node_id=OuterRef("meshtastic_node_id")).values("short_name")[:1]
    obs_long = ObservedNode.objects.filter(meshtastic_node_id=OuterRef("meshtastic_node_id")).values("long_name")[:1]
    latest_lat = NodeLatestStatus.objects.filter(node__meshtastic_node_id=OuterRef("meshtastic_node_id")).values(
        "latitude"
    )[:1]
    latest_lng = NodeLatestStatus.objects.filter(node__meshtastic_node_id=OuterRef("meshtastic_node_id")).values(
        "longitude"
    )[:1]
    return eligible.annotate(
        observed_short_name=Subquery(obs_short),
        observed_long_name=Subquery(obs_long),
        observed_latitude=Subquery(latest_lat),
        observed_longitude=Subquery(latest_lng),
    ).order_by("meshtastic_node_id")
