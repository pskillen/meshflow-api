"""Service for processing traceroute response packets."""

import logging
import os
from datetime import timedelta

from django.utils import timezone

from packets.models import TraceroutePacket
from packets.services.base import BasePacketService
from packets.signals import auto_traceroute_completed_from_packet
from traceroute.lifecycle import (
    apply_auto_traceroute_completion,
    create_external_inferred_auto_traceroute,
)
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
                self.from_node.meshtastic_node_id,
            )
            auto_tr = create_external_inferred_auto_traceroute(
                source_node=source_node,
                target_node=self.from_node,
            )

        route = []
        for i, nid in enumerate(self.packet.route):
            snr = self.packet.snr_towards[i] if i < len(self.packet.snr_towards) else None
            route.append({"node_id": nid, "snr": snr})
        route_back = []
        for i, nid in enumerate(self.packet.route_back):
            snr = self.packet.snr_back[i] if i < len(self.packet.snr_back) else None
            route_back.append({"node_id": nid, "snr": snr})

        apply_auto_traceroute_completion(
            auto_tr,
            route=route,
            route_back=route_back,
            raw_packet=self.packet,
        )

        auto_traceroute_completed_from_packet.send(
            sender=self.__class__,
            auto_tr=auto_tr,
            traceroute_packet=self.packet,
            packet_observation=self.observation,
            observer=self.observer,
            from_node=self.from_node,
        )
        logger.info("Linked TraceroutePacket %s to AutoTraceRoute %s", self.packet.id, auto_tr.id)
