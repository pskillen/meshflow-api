"""Service for processing traceroute response packets."""

import logging
import os
from datetime import timedelta

from django.utils import timezone

from packets.models import TraceroutePacket
from packets.services.base import BasePacketService
from traceroute.models import AutoTraceRoute

logger = logging.getLogger(__name__)

STALE_TR_TIMEOUT_SECONDS = int(os.environ.get("STALE_TR_TIMEOUT_SECONDS", "180"))


class TraceroutePacketService(BasePacketService):
    """Link traceroute responses to AutoTraceRoute and complete them (same pattern as other packet services)."""

    packet: TraceroutePacket

    def _process_packet(self) -> None:
        if not isinstance(self.packet, TraceroutePacket):
            raise ValueError("Packet must be a TraceroutePacket")

        source_node = self.observer
        cutoff = timezone.now() - timedelta(seconds=STALE_TR_TIMEOUT_SECONDS)

        auto_tr = (
            AutoTraceRoute.objects.filter(
                source_node=source_node,
                target_node=self.from_node,
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
            logger.info(
                "No AutoTraceRoute found for packet %s from %s to %s; creating external record",
                self.packet.id,
                source_node.node_id_str,
                self.from_node.node_id,
            )
            auto_tr = AutoTraceRoute.objects.create(
                source_node=source_node,
                target_node=self.from_node,
                trigger_type=AutoTraceRoute.TRIGGER_TYPE_EXTERNAL,
                trigger_source=None,
                triggered_by=None,
                triggered_at=timezone.now(),
                status=AutoTraceRoute.STATUS_PENDING,
            )

        route = []
        for i, nid in enumerate(self.packet.route):
            snr = self.packet.snr_towards[i] if i < len(self.packet.snr_towards) else None
            route.append({"node_id": nid, "snr": snr})
        route_back = []
        for i, nid in enumerate(self.packet.route_back):
            snr = self.packet.snr_back[i] if i < len(self.packet.snr_back) else None
            route_back.append({"node_id": nid, "snr": snr})

        auto_tr.status = AutoTraceRoute.STATUS_COMPLETED
        auto_tr.route = route
        auto_tr.route_back = route_back
        auto_tr.raw_packet = self.packet
        auto_tr.completed_at = timezone.now()
        auto_tr.error_message = None
        auto_tr.save(
            update_fields=["status", "route", "route_back", "raw_packet", "completed_at", "error_message"],
        )

        # Lazy imports so tests can patch traceroute.tasks / traceroute.ws_notify / mesh_monitoring.services.
        from mesh_monitoring.services import on_monitoring_traceroute_completed
        from traceroute.tasks import push_traceroute_to_neo4j
        from traceroute.ws_notify import notify_traceroute_status_changed

        on_monitoring_traceroute_completed(auto_tr)
        notify_traceroute_status_changed(auto_tr.id, AutoTraceRoute.STATUS_COMPLETED)
        push_traceroute_to_neo4j.delay(auto_tr.id)
        logger.info("Linked TraceroutePacket %s to AutoTraceRoute %s", self.packet.id, auto_tr.id)
