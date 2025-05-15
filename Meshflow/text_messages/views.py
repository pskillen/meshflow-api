from django.db import models

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from common.mesh_node_helpers import BROADCAST_ID
from nodes.models import ManagedNode, ObservedNode
from packets.models import PacketObservation

from .models import TextMessage
from .serializers import TextMessageSerializer


class TextMessageViewSet(viewsets.ModelViewSet):
    serializer_class = TextMessageSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "delete", "head", "options"]

    def get_queryset(self):
        queryset = TextMessage.objects.select_related("sender", "original_packet").all().order_by("-sent_at")

        constellation_id = self.request.query_params.get("constellation_id")
        channel_id = self.request.query_params.get("channel_id")
        if constellation_id:
            queryset = queryset.filter(channel__constellation_id=constellation_id)
        if channel_id:
            queryset = queryset.filter(channel_id=channel_id)

        # filter out any DMs (i.e. recipient_node_id must be '^all')
        queryset = queryset.filter(recipient_node_id=BROADCAST_ID)

        # Prefetch observations and their observer for each original_packet
        observation_qs = PacketObservation.objects.select_related("observer")
        queryset = queryset.prefetch_related(
            models.Prefetch("original_packet__observations", queryset=observation_qs, to_attr="prefetched_observations")
        )

        # NB: Keeping this prefetch for posterity - it's not needed because we're using the observer_nodes_map
        #     It also doesn't work because ManagedNode doesn't have a formal FK to ObservedNode
        # # Prefetch ObservedNode for all observer nodes referenced by PacketObservation
        # observer_node_ids = PacketObservation.objects.values_list("observer_id", flat=True).distinct()
        # observed_nodes = ObservedNode.objects.filter(node_id__in=observer_node_ids)
        # queryset = queryset.prefetch_related(
        #     models.Prefetch("original_packet__observations__observer__observednode_set",
        #                     queryset=observed_nodes, to_attr="prefetched_observed_nodes")
        # )

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Build a mapping of node_id -> ObservedNode for all relevant nodes
        observer_node_ids = ManagedNode.objects.values_list("node_id", flat=True).distinct()
        observed_nodes = ObservedNode.objects.filter(node_id__in=observer_node_ids)
        context["observer_nodes_map"] = {n.node_id: n for n in observed_nodes}
        return context
