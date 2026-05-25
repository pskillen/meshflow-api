from django.shortcuts import get_object_or_404

from rest_framework import mixins, permissions, status, viewsets
from rest_framework.response import Response

from common.drf_permissions import AllowGuestReadOnly, IsSystemAdmin
from common.protocol import protocol_from_query_param
from Meshflow.permissions import NoPermission

from .models import Constellation, MessageChannel
from .serializers import ConstellationSerializer, MessageChannelSerializer


class ConstellationViewSet(viewsets.ModelViewSet):
    """
    Constellations are public for read (guest or authenticated).
    Writes require Django staff.
    """

    serializer_class = ConstellationSerializer
    queryset = Constellation.objects.all().order_by("id")

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowGuestReadOnly()]
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsSystemAdmin()]
        return [NoPermission()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == "list":
            context["channel_protocol_filter"] = protocol_from_query_param(self.request.query_params.get("protocol"))
        return context

    def get_queryset(self):
        qs = Constellation.objects.all().order_by("id")
        if self.action == "list":
            protocol_val = protocol_from_query_param(self.request.query_params.get("protocol"))
            if protocol_val is not None:
                qs = qs.filter(protocol=protocol_val)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ConstellationMessageChannelsViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
):
    """
    Message channels: public list; staff-only mutations.
    """

    serializer_class = MessageChannelSerializer
    permission_classes = [AllowGuestReadOnly]

    def get_queryset(self):
        constellation_id = self.kwargs.get("constellation_id")
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        qs = MessageChannel.objects.filter(constellation=constellation).order_by("id")
        protocol_val = protocol_from_query_param(self.request.query_params.get("protocol"))
        if protocol_val is not None:
            qs = qs.filter(protocol=protocol_val)
        return qs

    def get_permissions(self):
        if self.action == "list":
            return [AllowGuestReadOnly()]
        return [IsSystemAdmin()]

    def create(self, request, constellation_id=None):
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        data = request.data.copy()
        data["constellation"] = constellation.id
        serializer = MessageChannelSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, channel_id=None, constellation_id=None):
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        try:
            channel = MessageChannel.objects.get(id=channel_id, constellation=constellation)
        except MessageChannel.DoesNotExist:
            return Response({"detail": "Channel not found."}, status=status.HTTP_404_NOT_FOUND)
        data = request.data.copy()
        data["constellation"] = constellation.id
        serializer = MessageChannelSerializer(channel, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, channel_id=None, constellation_id=None):
        constellation = get_object_or_404(Constellation, pk=constellation_id)
        try:
            channel = MessageChannel.objects.get(id=channel_id, constellation=constellation)
        except MessageChannel.DoesNotExist:
            return Response({"detail": "Channel not found."}, status=status.HTTP_404_NOT_FOUND)
        channel.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
