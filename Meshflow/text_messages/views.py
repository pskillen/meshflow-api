from django.db import models
from django.db.models import Q

from rest_framework import viewsets

from common.drf_permissions import AllowGuestReadOnly, IsAuthenticatedUser
from common.mesh_node_helpers import MESHTASTIC_BROADCAST_ID
from common.protocol import Protocol
from nodes.models import ManagedNode, ObservedNode
from packets.models import PacketObservation

from .models import TextMessage
from .serializers import TextMessageSerializer


class TextMessageViewSet(viewsets.ModelViewSet):
    serializer_class = TextMessageSerializer
    http_method_names = ["get", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowGuestReadOnly()]
        return [IsAuthenticatedUser()]

    def get_queryset(self):
        queryset = (
            TextMessage.objects.select_related(
                "sender",
                "original_packet",
                "original_mc_packet",
                "channel",
            )
            .all()
            .order_by("-sent_at")
        )

        constellation_id = self.request.query_params.get("constellation_id")
        channel_id = self.request.query_params.get("channel_id")
        sender_node_id = self.request.query_params.get("sender_node_id")
        protocol_param = self.request.query_params.get("protocol")

        if constellation_id:
            queryset = queryset.filter(channel__constellation_id=constellation_id)
        if channel_id:
            queryset = queryset.filter(channel_id=channel_id)
        if sender_node_id:
            queryset = queryset.filter(sender__meshtastic_node_id=int(sender_node_id))
        if protocol_param:
            key = protocol_param.strip().lower()
            if key in ("meshtastic", "mt", "1"):
                queryset = queryset.filter(protocol=Protocol.MESHTASTIC)
            elif key in ("meshcore", "mc", "2"):
                queryset = queryset.filter(protocol=Protocol.MESHCORE)

        queryset = queryset.filter(
            Q(protocol=Protocol.MESHTASTIC, recipient_meshtastic_node_id=MESHTASTIC_BROADCAST_ID)
            | Q(protocol=Protocol.MESHCORE, sender__isnull=True, channel__isnull=False)
        )

        observation_qs = PacketObservation.objects.select_related("observer")
        queryset = queryset.prefetch_related(
            models.Prefetch("original_packet__observations", queryset=observation_qs, to_attr="prefetched_observations")
        )

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        observer_node_ids = (
            ManagedNode.objects.filter(deleted_at__isnull=True).values_list("meshtastic_node_id", flat=True).distinct()
        )
        observed_nodes = ObservedNode.objects.filter(meshtastic_node_id__in=observer_node_ids)
        context["observer_nodes_map"] = {n.meshtastic_node_id: n for n in observed_nodes}
        return context
