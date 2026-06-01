"""MeshCore packet API views."""

import logging

from django.utils import timezone

from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.feeder_ws import COMMAND_DISPATCH_UNAVAILABLE, FEEDER_BOT_NOT_CONNECTED
from meshcore_packets.models import MeshCoreRawPacket, MeshCoreTextPacket
from meshcore_packets.permissions import MeshCoreFeederPermission
from meshcore_packets.serializers import MeshCorePacketIngestSerializer, MeshCorePacketListSerializer
from meshcore_packets.serializers_channel import (
    FeederMcChannelMirrorSerializer,
    McChannelApplySerializer,
    McChannelSyncSerializer,
)
from meshcore_packets.services.channel_apply import apply_mc_channels_to_feeder
from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.signals import meshcore_packet_received, meshcore_text_packet_received
from nodes.authentication import NodeAPIKeyAuthentication
from nodes.models import ManagedNode

logger = logging.getLogger(__name__)


class MeshCoreFeederBotVersionSerializer(serializers.Serializer):
    """Body for feeder-reported meshflow-bot version."""

    bot_version = serializers.CharField(max_length=128, trim_whitespace=True)


class MeshCoreFeederBotConfigView(APIView):
    """Return operator config for the meshflow-bot linked to this MeshCore feeder."""

    authentication_classes = [NodeAPIKeyAuthentication]
    permission_classes = [MeshCoreFeederPermission]

    def get(self, request, feeder_pubkey_prefix, format=None):
        managed_node = request.auth.node
        return Response(
            {
                "mc_flood_advert_interval_hours": managed_node.mc_flood_advert_interval_hours,
            },
            status=status.HTTP_200_OK,
        )


class MeshCoreFeederBotVersionView(APIView):
    """Update bot_version for the MeshCore feeder identified in the URL prefix."""

    authentication_classes = [NodeAPIKeyAuthentication]
    permission_classes = [MeshCoreFeederPermission]

    def put(self, request, feeder_pubkey_prefix, format=None):
        return self._update(request)

    def post(self, request, feeder_pubkey_prefix, format=None):
        return self._update(request)

    def patch(self, request, feeder_pubkey_prefix, format=None):
        return self._update(request)

    def _update(self, request):
        managed_node = request.auth.node
        serializer = MeshCoreFeederBotVersionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        bot_version = serializer.validated_data["bot_version"]
        if not bot_version:
            return Response(
                {"bot_version": ["This field may not be blank."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        managed_node.bot_version = bot_version
        managed_node.bot_version_reported_at = now
        managed_node.save(update_fields=["bot_version", "bot_version_reported_at"])

        return Response(
            {
                "status": "success",
                "bot_version": managed_node.bot_version,
                "bot_version_reported_at": managed_node.bot_version_reported_at,
            },
            status=status.HTTP_200_OK,
        )


class MeshCorePacketIngestView(APIView):
    """POST ingest for MeshCore feeder bots (API key + feeder pubkey prefix in URL)."""

    authentication_classes = [NodeAPIKeyAuthentication]
    permission_classes = [MeshCoreFeederPermission]

    def post(self, request, feeder_pubkey_prefix, format=None):
        if request.data.get("encrypted"):
            return Response(
                {"status": "success", "message": "Encrypted packet skipped"},
                status=status.HTTP_304_NOT_MODIFIED,
            )

        observer = request.auth.node
        serializer = MeshCorePacketIngestSerializer(
            data=request.data,
            context={"observer": observer},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        packet = serializer.save()
        observation = serializer.observation
        meshcore_packet_received.send(
            sender=self,
            packet=packet,
            observer=observer,
            observation=observation,
        )
        if isinstance(packet, MeshCoreTextPacket):
            meshcore_text_packet_received.send(
                sender=self,
                packet=packet,
                observer=observer,
                observation=observation,
            )

        return Response(
            {"status": "success", "packet_id": str(packet.id)},
            status=status.HTTP_201_CREATED,
        )


class MeshCorePacketListView(generics.ListAPIView):
    """Read-only list of ingested MeshCore packets (JWT/session auth)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MeshCorePacketListSerializer
    queryset = MeshCoreRawPacket.objects.select_related("observer").order_by("-rx_time")

    def get_queryset(self):
        qs = super().get_queryset()
        payload_type = self.request.query_params.get("payload_type")
        if payload_type:
            qs = qs.filter(payload_type=payload_type)
        prefix = self.request.query_params.get("from_pubkey_prefix")
        if prefix:
            qs = qs.filter(from_pubkey_prefix=prefix.lower())
        observer_id = self.request.query_params.get("observer")
        if observer_id:
            qs = qs.filter(observer__internal_id=observer_id)
        return qs


class MeshCoreMcChannelSyncView(APIView):
    """POST device channel snapshot from feeder bot; reconciles API mirror."""

    authentication_classes = [NodeAPIKeyAuthentication]
    permission_classes = [MeshCoreFeederPermission]

    def post(self, request, feeder_pubkey_prefix, format=None):
        managed_node = request.auth.node
        serializer = McChannelSyncSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            reconcile_mc_channels(
                managed_node,
                serializer.validated_data["channels"],
                synced_at=serializer.validated_data.get("synced_at"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        managed_node.refresh_from_db()
        return Response(
            {
                "status": "success",
                "synced_at": managed_node.mc_channels_synced_at,
                "mc_channels": FeederMcChannelMirrorSerializer(
                    managed_node.mc_channel_links.select_related("message_channel").order_by("mc_channel_idx"),
                    many=True,
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class ManagedNodeMcChannelApplyView(APIView):
    """POST desired MC channels; pushes apply_mc_channel_config to connected feeder bot."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, internal_id, format=None):
        managed_node = ManagedNode.objects.filter(
            internal_id=internal_id,
            deleted_at__isnull=True,
            owner=request.user,
        ).first()
        if not managed_node:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = McChannelApplySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        channels = serializer.validated_data["channels"]
        result = apply_mc_channels_to_feeder(managed_node, channels)
        if result == FEEDER_BOT_NOT_CONNECTED:
            return Response(
                {
                    "detail": (
                        "Feeder bot is not connected via WebSocket. "
                        "Start the bot with MESHCORE_UPLOAD_ENABLED and MESHFLOW_WS_URL configured. "
                        "For shared API keys, the bot must connect with "
                        "feeder_pubkey_prefix in the WebSocket URL (same 12-hex prefix as ingest)."
                    ),
                    "code": FEEDER_BOT_NOT_CONNECTED,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if result == COMMAND_DISPATCH_UNAVAILABLE:
            return Response(
                {
                    "detail": ("Could not dispatch command to the feeder (channel layer / Redis unavailable)."),
                    "code": COMMAND_DISPATCH_UNAVAILABLE,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "status": "dispatched",
                "message": "apply_mc_channel_config sent to connected bot; device sync updates API mirror.",
            },
            status=status.HTTP_202_ACCEPTED,
        )
