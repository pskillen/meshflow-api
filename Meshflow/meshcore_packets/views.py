"""MeshCore packet API views."""

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from meshcore_packets.models import MeshCoreRawPacket, MeshCoreTextPacket
from meshcore_packets.permissions import MeshCoreFeederPermission
from meshcore_packets.serializers import MeshCorePacketIngestSerializer, MeshCorePacketListSerializer
from meshcore_packets.signals import meshcore_packet_received, meshcore_text_packet_received
from nodes.authentication import NodeAPIKeyAuthentication


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
