"""Aggregate monitoring alert counts for UI (e.g. Mesh Infra nav badge)."""

from django.db.models import Q

from nodes.constants import INFRASTRUCTURE_ROLES
from nodes.models import ObservedNode


def mesh_infra_monitoring_alert_counts():
    """
    Count infrastructure observed nodes in an alerting monitoring state.

    ``alerting_nodes_count`` is the distinct union of offline, active battery alert, and verifying nodes.
    """
    qs = ObservedNode.objects.filter(role__in=INFRASTRUCTURE_ROLES)

    offline_q = Q(mesh_presence__is_offline=True) | Q(mesh_presence__offline_confirmed_at__isnull=False)
    battery_q = Q(monitoring_config__battery_alert_enabled=True) & Q(
        mesh_presence__battery_alert_confirmed_at__isnull=False
    )
    verifying_q = (
        Q(mesh_presence__verification_started_at__isnull=False)
        & Q(mesh_presence__offline_confirmed_at__isnull=True)
        & Q(mesh_presence__is_offline=False)
    )

    offline_count = qs.filter(offline_q).distinct().count()
    battery_count = qs.filter(battery_q).distinct().count()
    verifying_count = qs.filter(verifying_q).distinct().count()
    alerting_nodes_count = qs.filter(offline_q | battery_q | verifying_q).distinct().count()

    return {
        "alerting_nodes_count": alerting_nodes_count,
        "offline_count": offline_count,
        "battery_count": battery_count,
        "verifying_count": verifying_count,
    }
