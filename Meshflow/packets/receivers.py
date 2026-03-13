import logging

from django.dispatch import receiver
from django.utils import timezone

from nodes.models import ObservedNode

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
    node_info_packet_received,
    position_packet_received,
    power_metrics_packet_received,
    traceroute_packet_received,
    traffic_management_stats_packet_received,
)

logger = logging.getLogger(__name__)


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
    """Handle a traceroute packet received signal. Link to pending AutoTraceRoute if match."""
    logger.info(f"Traceroute packet received: {packet.id}")

    from traceroute.models import AutoTraceRoute

    # observer is ManagedNode (from PacketObservation)
    source_node = observer
    target_node_id = packet.from_int  # TR response: from = target (who sent the response)
    cutoff = timezone.now() - timezone.timedelta(seconds=120)

    auto_tr = (
        AutoTraceRoute.objects.filter(
            source_node=source_node,
            target_node__node_id=target_node_id,
            triggered_at__gte=cutoff,
            status__in=[AutoTraceRoute.STATUS_PENDING, AutoTraceRoute.STATUS_SENT],
        )
        .order_by("-triggered_at")
        .first()
    )

    if not auto_tr:
        logger.warning(
            f"No AutoTraceRoute found for packet {packet.id} from {source_node.node_id_str} to {target_node_id}"
        )
        return

    # Build route/route_back with SNR: TraceroutePacket has route, route_back (node_ids) and snr_towards, snr_back
    route = []
    for i, nid in enumerate(packet.route):
        snr = packet.snr_towards[i] if i < len(packet.snr_towards) else None
        route.append({"node_id": nid, "snr": snr})
    route_back = []
    for i, nid in enumerate(packet.route_back):
        snr = packet.snr_back[i] if i < len(packet.snr_back) else None
        route_back.append({"node_id": nid, "snr": snr})

    # Empty route+route_back indicates timeout/failure from device; mark failed rather than completed
    if not route and not route_back:
        auto_tr.status = AutoTraceRoute.STATUS_FAILED
        auto_tr.route = route
        auto_tr.route_back = route_back
        auto_tr.raw_packet = packet
        auto_tr.completed_at = timezone.now()
        auto_tr.error_message = "Timed out"
        auto_tr.save(update_fields=["status", "route", "route_back", "raw_packet", "completed_at", "error_message"])

        from traceroute.ws_notify import notify_traceroute_status_changed

        notify_traceroute_status_changed(auto_tr.id, AutoTraceRoute.STATUS_FAILED)
        logger.info(f"Linked TraceroutePacket {packet.id} to AutoTraceRoute {auto_tr.id} (failed: empty route)")
    else:
        auto_tr.status = AutoTraceRoute.STATUS_COMPLETED
        auto_tr.route = route
        auto_tr.route_back = route_back
        auto_tr.raw_packet = packet
        auto_tr.completed_at = timezone.now()
        auto_tr.save(update_fields=["status", "route", "route_back", "raw_packet", "completed_at"])

        from traceroute.ws_notify import notify_traceroute_status_changed

        notify_traceroute_status_changed(auto_tr.id, AutoTraceRoute.STATUS_COMPLETED)
        logger.info(f"Linked TraceroutePacket {packet.id} to AutoTraceRoute {auto_tr.id}")
