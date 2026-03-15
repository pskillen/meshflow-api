"""Shared permission logic for traceroute triggering."""

from django.db.models import OuterRef, Q, Subquery

from constellations.models import ConstellationUserMembership
from nodes.models import ManagedNode, ObservedNode


def user_can_trigger_from_node(user, source_node):
    """Check if user can trigger a traceroute from the given ManagedNode."""
    if user.is_staff:
        return True
    if source_node.owner_id == user.id:
        return True
    return ConstellationUserMembership.objects.filter(
        user=user,
        constellation=source_node.constellation,
        role__in=["admin", "editor"],
    ).exists()


def get_triggerable_nodes_queryset(user):
    """Return ManagedNodes the user can trigger traceroutes from (allow_auto_traceroute=True)."""
    base = ManagedNode.objects.filter(allow_auto_traceroute=True).select_related("constellation")
    if user.is_staff:
        qs = base
    else:
        constellation_ids = ConstellationUserMembership.objects.filter(
            user=user, role__in=["admin", "editor"]
        ).values_list("constellation_id", flat=True)
        qs = base.filter(Q(owner=user) | Q(constellation_id__in=constellation_ids)).distinct()
    obs_short = ObservedNode.objects.filter(node_id=OuterRef("node_id")).values("short_name")[:1]
    obs_long = ObservedNode.objects.filter(node_id=OuterRef("node_id")).values("long_name")[:1]
    return qs.annotate(
        observed_short_name=Subquery(obs_short),
        observed_long_name=Subquery(obs_long),
    ).order_by("node_id")
