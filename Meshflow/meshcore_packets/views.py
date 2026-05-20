"""MeshCore packet API views."""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

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


def _dispatch_mc_channel_apply(managed_node: ManagedNode, channels: list[dict]) -> bool:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return False
    group = managed_node_ws_group(managed_node)
    async_to_sync(channel_layer.group_send)(
        group,
        {
            "type": "node_command",
            "command": {
                "type": "apply_mc_channel_config",
                "channels": channels,
            },
        },
    )
    return True


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
        sent = _dispatch_mc_channel_apply(managed_node, channels)
        if not sent:
            return Response(
                {"detail": "WebSocket channel layer unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "status": "dispatched",
                "message": "apply_mc_channel_config sent to connected bot; device sync updates API mirror.",
            },
            status=status.HTTP_202_ACCEPTED,
        )
