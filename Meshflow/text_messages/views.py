from django.db import models
from django.db.models import Q

from rest_framework import viewsets
from rest_framework.response import Response

from common.drf_permissions import AllowGuestReadOnly, IsAuthenticatedUser
from common.mesh_node_helpers import MESHTASTIC_BROADCAST_ID
from common.protocol import Protocol
from meshcore_packets.models import MeshCorePacketObservation
from meshcore_packets.services.path_resolution import bulk_format_path_hops
from nodes.models import ManagedNode, ObservedNode
from packets.models import PacketObservation

from .mc_channel_sender import bulk_mc_sender_candidates_by_label, parse_mc_channel_sender_label
from .models import TextMessage
from .serializers import TextMessageSerializer, _normalize_path_segment


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
                "sender__latest_status",
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

        mt_observation_qs = PacketObservation.objects.select_related("observer")
        mc_observation_qs = MeshCorePacketObservation.objects.select_related("observer")
        queryset = queryset.prefetch_related(
            models.Prefetch(
                "original_packet__observations",
                queryset=mt_observation_qs,
                to_attr="prefetched_observations",
            ),
            models.Prefetch(
                "original_mc_packet__observations",
                queryset=mc_observation_qs,
                to_attr="prefetched_mc_observations",
            ),
        )

        return queryset

    def _mc_sender_labels_for_messages(self, messages):
        labels = set()
        for msg in messages:
            if msg.protocol == Protocol.MESHCORE and not msg.sender_id:
                label = parse_mc_channel_sender_label(msg.message_text)
                if label:
                    labels.add(label)
        return labels

    def _path_segment_refs_for_messages(self, messages):
        refs = []
        for msg in messages:
            if msg.protocol != Protocol.MESHCORE or not msg.original_mc_packet_id:
                continue
            packet = msg.original_mc_packet
            observations = getattr(packet, "prefetched_mc_observations", None) or []
            for obs in observations:
                if obs.path_hashes:
                    for segment in obs.path_hashes:
                        refs.append(
                            {
                                "segment": _normalize_path_segment(segment),
                                "hash_mode": obs.path_hash_mode,
                                "hash_size": obs.path_hash_size,
                            }
                        )
        return refs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        messages = page if page is not None else list(queryset)
        context = self.get_serializer_context()
        context["path_hop_cache"] = bulk_format_path_hops(self._path_segment_refs_for_messages(messages))
        context["mc_sender_candidates_by_label"] = bulk_mc_sender_candidates_by_label(
            self._mc_sender_labels_for_messages(messages)
        )
        serializer = self.get_serializer(messages, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        observer_node_ids = (
            ManagedNode.objects.filter(deleted_at__isnull=True).values_list("meshtastic_node_id", flat=True).distinct()
        )
        observed_nodes = ObservedNode.objects.filter(meshtastic_node_id__in=observer_node_ids).select_related(
            "latest_status",
        )
        context["observer_nodes_map"] = {n.meshtastic_node_id: n for n in observed_nodes}

        mc_pubkeys = (
            ManagedNode.objects.filter(
                deleted_at__isnull=True,
                protocol=Protocol.MESHCORE,
                mc_pubkey__isnull=False,
            )
            .values_list("mc_pubkey", flat=True)
            .distinct()
        )
        mc_observed = ObservedNode.objects.filter(protocol=Protocol.MESHCORE, mc_pubkey__in=mc_pubkeys).select_related(
            "latest_status",
        )
        context["mc_observed_by_pubkey"] = {node.mc_pubkey.lower(): node for node in mc_observed if node.mc_pubkey}
        return context
