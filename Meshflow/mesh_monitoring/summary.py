"""Aggregate monitoring alert counts for UI (e.g. Mesh Infra nav badge)."""

from django.db.models import Q

from common.protocol import Protocol
from nodes.constants import INFRASTRUCTURE_ROLES, MC_INFRA
from nodes.models import ObservedNode


def mesh_infra_monitoring_alert_counts(protocol=Protocol.MESHTASTIC):
    """
    Count infrastructure observed nodes of ``protocol`` in an alerting monitoring state.

    Meshtastic infra = ``meshtastic_role`` in ``INFRASTRUCTURE_ROLES``; MeshCore infra =
    ``meshcore_adv_type`` in ``MC_INFRA``. ``supported`` is False for MeshCore because mesh_presence
    monitoring (offline / battery / verifying) does not run for MeshCore nodes yet, so zero counts mean
    "not monitored", not "all healthy".

    ``alerting_nodes_count`` is the distinct union of offline, active battery alert, and verifying nodes.
    """
    if protocol == Protocol.MESHCORE:
        qs = ObservedNode.objects.filter(protocol=Protocol.MESHCORE, meshcore_adv_type__in=MC_INFRA)
    else:
        protocol = Protocol.MESHTASTIC
        qs = ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_role__in=INFRASTRUCTURE_ROLES)

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
        "protocol": "meshcore" if protocol == Protocol.MESHCORE else "meshtastic",
        "supported": protocol == Protocol.MESHTASTIC,
        "alerting_nodes_count": alerting_nodes_count,
        "offline_count": offline_count,
        "battery_count": battery_count,
        "verifying_count": verifying_count,
    }
