import logging
import os

from django.dispatch import receiver
from django.utils import timezone

from common.mesh_node_helpers import meshtastic_id_to_hex
from constellations.models import ConstellationUserMembership
from nodes.models import NodeLatestStatus, ObservedNode

from .models import (
    AirQualityMetricsPacket,
    DeviceMetricsPacket,
    EnvironmentMetricsPacket,
    HealthMetricsPacket,
    HostMetricsPacket,
    MessagePacket,
    NodeInfoPacket,
    PacketObservation,
    PositionPacket,
    PowerMetricsPacket,
    TraceroutePacket,
    TrafficManagementStatsPacket,
)
from .services.air_quality import AirQualityMetricsPacketService
from .services.device_metrics import DeviceMetricsPacketService
from .services.environment_metrics import EnvironmentMetricsPacketService
from .services.health_metrics import HealthMetricsPacketService
from .services.host_metrics import HostMetricsPacketService
from .services.node_info import NodeInfoPacketService
from .services.position import PositionPacketService
from .services.power_metrics import PowerMetricsPacketService
from .services.text_message import TextMessagePacketService
from .signals import (
    air_quality_metrics_packet_received,
    device_metrics_packet_received,
    environment_metrics_packet_received,
    health_metrics_packet_received,
    host_metrics_packet_received,
    message_packet_received,
    new_node_observed,
    node_claim_authorized,
    node_info_packet_received,
    packet_received,
    position_packet_received,
    power_metrics_packet_received,
    traceroute_packet_received,
    traffic_management_stats_packet_received,
)

logger = logging.getLogger(__name__)

STALE_TR_TIMEOUT_SECONDS = os.environ.get("STALE_TR_TIMEOUT_SECONDS", 180)


# Packet types that already update NodeLatestStatus (and set inferred_max_hops there)
_PACKET_TYPES_WITH_NLS_UPDATE = (
    PositionPacket,
    DeviceMetricsPacket,
    EnvironmentMetricsPacket,
    PowerMetricsPacket,
    HealthMetricsPacket,
    HostMetricsPacket,
    AirQualityMetricsPacket,
)


@receiver(packet_received)
def on_packet_received_update_inferred_max_hops(sender, packet, observer, observation, **kwargs):
    """Update NodeLatestStatus.inferred_max_hops for packet types that don't update NodeLatestStatus."""
    if isinstance(packet, _PACKET_TYPES_WITH_NLS_UPDATE):
        return
    hop_start = observation.hop_start if observation else None
    if hop_start is None:
        return
    sender_node_id = getattr(packet, "from_int", None)
    if sender_node_id is None:
        return
    node_id_str = getattr(packet, "from_str", None) or meshtastic_id_to_hex(sender_node_id)
    observed_node, _ = ObservedNode.objects.get_or_create(
        node_id=sender_node_id,
        defaults={
            "node_id_str": node_id_str,
            "long_name": "Unknown Node " + node_id_str,
            "short_name": node_id_str[-4:] if len(node_id_str) >= 4 else "????",
        },
    )
    node_status, created = NodeLatestStatus.objects.get_or_create(
        node=observed_node,
        defaults={"inferred_max_hops": hop_start},
    )
    if not created and node_status.inferred_max_hops != hop_start:
        node_status.inferred_max_hops = hop_start
        node_status.save(update_fields=["inferred_max_hops"])


STALE_TR_TIMEOUT_SECONDS = os.environ.get("STALE_TR_TIMEOUT_SECONDS", 180)
STALE_TR_TIMEOUT_SECONDS = int(STALE_TR_TIMEOUT_SECONDS)


@receiver(position_packet_received)
def position_packet_received(
    sender, packet: PositionPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a position packet received signal."""
    logger.info(f"Position packet received: {packet.id}")

    service = PositionPacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(device_metrics_packet_received)
def device_metrics_packet_received(
    sender, packet: DeviceMetricsPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a device metrics packet received signal."""
    logger.info(f"Device metrics packet received: {packet.id}")

    service = DeviceMetricsPacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(message_packet_received)
def message_packet_received(
    sender, packet: MessagePacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a message packet received signal."""
    logger.info(f"Message packet received: {packet.id}")

    service = TextMessagePacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(node_claim_authorized)
def on_node_claim_authorized_add_user_to_constellation(sender, node, claim, observer, **kwargs):
    """Add the claiming user to the observer's constellation as a viewer."""
    ConstellationUserMembership.objects.get_or_create(
        user=claim.user,
        constellation=observer.constellation,
        defaults={"role": "viewer"},
    )


@receiver(node_info_packet_received)
def node_info_packet_received(
    sender, packet: NodeInfoPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a node info packet received signal."""
    logger.info(f"Node info packet received: {packet.id}")

    service = NodeInfoPacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(environment_metrics_packet_received)
def on_environment_metrics_packet_received(
    sender, packet: EnvironmentMetricsPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle an environment metrics packet received signal."""
    logger.info(f"Environment metrics packet received: {packet.id}")
    service = EnvironmentMetricsPacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(air_quality_metrics_packet_received)
def on_air_quality_metrics_packet_received(
    sender, packet: AirQualityMetricsPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle an air quality metrics packet received signal."""
    logger.info(f"Air quality metrics packet received: {packet.id}")
    service = AirQualityMetricsPacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(health_metrics_packet_received)
def on_health_metrics_packet_received(
    sender, packet: HealthMetricsPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a health metrics packet received signal."""
    logger.info(f"Health metrics packet received: {packet.id}")
    service = HealthMetricsPacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(host_metrics_packet_received)
def on_host_metrics_packet_received(
    sender, packet: HostMetricsPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a host metrics packet received signal."""
    logger.info(f"Host metrics packet received: {packet.id}")
    service = HostMetricsPacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(power_metrics_packet_received)
def on_power_metrics_packet_received(
    sender, packet: PowerMetricsPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a power metrics packet received signal."""
    logger.info(f"Power metrics packet received: {packet.id}")
    service = PowerMetricsPacketService()
    service.process_packet(packet, observer, observation, user=None)


@receiver(traffic_management_stats_packet_received)
def on_traffic_management_stats_packet_received(
    sender, packet: TrafficManagementStatsPacket, observer: ObservedNode, observation: PacketObservation, **kwargs
):
    """Handle a traffic management stats packet received signal. Packet is stored by serializer; no service."""
    logger.info(f"Traffic management stats packet received: {packet.id}")


@receiver(traceroute_packet_received)
def on_traceroute_packet_received(sender, packet: TraceroutePacket, observer, observation: PacketObservation, **kwargs):
    """Handle a traceroute packet received signal. Link to AutoTraceRoute if match, or infer one for cross-env.

    Any ingested traceroute response is treated as completed: empty ``route``/``route_back`` means a direct RF
    path (no intermediate hops per Meshtastic firmware), not a timeout. True no-response remains ``pending``/``sent``
    until ``mark_stale_traceroutes_failed`` runs.
    """
    logger.info(f"Traceroute packet received: {packet.id}")

    from traceroute.models import AutoTraceRoute

    # observer is ManagedNode (from PacketObservation)
    source_node = observer
    target_node_id = packet.from_int  # TR response: from = target (who sent the response)
    cutoff = timezone.now() - timezone.timedelta(seconds=STALE_TR_TIMEOUT_SECONDS)  # 5 minutes

    auto_tr = (
        AutoTraceRoute.objects.filter(
            source_node=source_node,
            target_node__node_id=target_node_id,
            triggered_at__gte=cutoff,
            status__in=[
                AutoTraceRoute.STATUS_PENDING,
                AutoTraceRoute.STATUS_SENT,
                AutoTraceRoute.STATUS_FAILED,
            ],
        )
        .order_by("-triggered_at")
        .first()
    )

    if not auto_tr:
        # No match within window: create external AutoTraceRoute (cross-env or orphaned response)
        logger.info(
            f"No AutoTraceRoute found for packet {packet.id} from {source_node.node_id_str} to {target_node_id}; "
            "creating external record"
        )
        node_id_str = packet.from_str if packet.from_str else meshtastic_id_to_hex(target_node_id)
        target_node, created = ObservedNode.objects.get_or_create(
            node_id=target_node_id,
            defaults={
                "node_id_str": node_id_str,
                "long_name": "Unknown Node " + node_id_str,
                "short_name": node_id_str[-4:] if len(node_id_str) >= 4 else "????",
            },
        )
        if created:
            new_node_observed.send(sender=None, node=target_node, observer=source_node)
        auto_tr = AutoTraceRoute.objects.create(
            source_node=source_node,
            target_node=target_node,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_EXTERNAL,
            trigger_source=None,
            triggered_by=None,
            triggered_at=timezone.now(),
            status=AutoTraceRoute.STATUS_PENDING,
        )

    # Build route/route_back with SNR: 1:1 mapping route[i] <-> snr_towards[i] (SNR at which route[i] received).
    # Per Meshtastic firmware PR #4485; firmware may send snr longer than route in edge cases — we use i < len.
    route = []
    for i, nid in enumerate(packet.route):
        snr = packet.snr_towards[i] if i < len(packet.snr_towards) else None
        route.append({"node_id": nid, "snr": snr})
    route_back = []
    for i, nid in enumerate(packet.route_back):
        snr = packet.snr_back[i] if i < len(packet.snr_back) else None
        route_back.append({"node_id": nid, "snr": snr})

    auto_tr.status = AutoTraceRoute.STATUS_COMPLETED
    auto_tr.route = route
    auto_tr.route_back = route_back
    auto_tr.raw_packet = packet
    auto_tr.completed_at = timezone.now()
    auto_tr.error_message = None
    auto_tr.save(
        update_fields=["status", "route", "route_back", "raw_packet", "completed_at", "error_message"],
    )

    from mesh_monitoring.services import on_monitoring_traceroute_completed
    from traceroute.tasks import push_traceroute_to_neo4j
    from traceroute.ws_notify import notify_traceroute_status_changed

    on_monitoring_traceroute_completed(auto_tr)
    notify_traceroute_status_changed(auto_tr.id, AutoTraceRoute.STATUS_COMPLETED)
    push_traceroute_to_neo4j.delay(auto_tr.id)
    logger.info(f"Linked TraceroutePacket {packet.id} to AutoTraceRoute {auto_tr.id}")
