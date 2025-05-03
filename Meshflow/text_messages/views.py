from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from common.mesh_node_helpers import BROADCAST_ID

from .models import TextMessage
from .serializers import TextMessageSerializer


class TextMessageViewSet(viewsets.ModelViewSet):
    serializer_class = TextMessageSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "delete", "head", "options"]

    def get_queryset(self):
        queryset = TextMessage.objects.select_related("sender").all().order_by("-sent_at")
        constellation_id = self.request.query_params.get("constellation_id")
        channel_id = self.request.query_params.get("channel_id")
        if constellation_id:
            queryset = queryset.filter(channel__constellation_id=constellation_id)
        if channel_id:
            queryset = queryset.filter(channel_id=channel_id)

        # filter out any DMs (recipient_node_id must be '^all')
        queryset = queryset.filter(recipient_node_id=BROADCAST_ID)

        return queryset
