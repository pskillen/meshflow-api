"""MeshCore packet API views."""

import logging

from asgiref.sync import async_to_sync
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.feeder_ws import (
    COMMAND_DISPATCH_UNAVAILABLE,
    FEEDER_BOT_NOT_CONNECTED,
    dispatch_node_command,
    feeder_ws_group_has_subscribers,
)
from common.ws_groups import managed_node_ws_group
from meshcore_packets.models import MeshCoreRawPacket, MeshCoreTextPacket
from meshcore_packets.permissions import MeshCoreFeederPermission
from meshcore_packets.serializers import MeshCorePacketIngestSerializer, MeshCorePacketListSerializer
from meshcore_packets.serializers_channel import (
    McChannelApplySerializer,
    McChannelSyncSerializer,
    MessageChannelMcSerializer,
)
from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.signals import meshcore_packet_received, meshcore_text_packet_received
from nodes.authentication import NodeAPIKeyAuthentication
from nodes.models import ManagedNode

logger = logging.getLogger(__name__)


class MeshCorePacketIngestView(APIView):
    """POST ingest for MeshCore feeder bots (API key auth, no URL node id)."""

    authentication_classes = [NodeAPIKeyAuthentication]
    permission_classes = [MeshCoreFeederPermission]

    def post(self, request, format=None):
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

    def post(self, request, format=None):
        managed_node = request.auth.node
        serializer = McChannelSyncSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            channels = reconcile_mc_channels(
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
                "mc_channels": MessageChannelMcSerializer(channels, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


def _dispatch_mc_channel_apply(managed_node: ManagedNode, channels: list[dict]) -> str:
    """Dispatch apply_mc_channel_config. Returns ``sent`` or an error code string."""
    group = managed_node_ws_group(managed_node)

    async def _check_and_send() -> str:
        try:
            if not await feeder_ws_group_has_subscribers(group):
                return FEEDER_BOT_NOT_CONNECTED
        except Exception as exc:
            logger.exception("MC channel apply: feeder presence check failed: %s", exc)
            return COMMAND_DISPATCH_UNAVAILABLE

        try:
            await dispatch_node_command(
                group,
                {
                    "type": "apply_mc_channel_config",
                    "channels": channels,
                },
            )
        except Exception as exc:
            logger.exception("MC channel apply: group_send failed: %s", exc)
            return COMMAND_DISPATCH_UNAVAILABLE
        return "sent"

    return async_to_sync(_check_and_send)()


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
        result = _dispatch_mc_channel_apply(managed_node, channels)
        if result == FEEDER_BOT_NOT_CONNECTED:
            return Response(
                {
                    "detail": (
                        "Feeder bot is not connected via WebSocket. "
                        "Start the bot with MESHCORE_UPLOAD_ENABLED and MESHFLOW_WS_URL configured."
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
