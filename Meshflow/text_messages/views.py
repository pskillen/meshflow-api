from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import TextMessage
from .serializers import TextMessageSerializer


class TextMessageViewSet(viewsets.ModelViewSet):
    queryset = TextMessage.objects.all().order_by("-sent_at")
    serializer_class = TextMessageSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "delete", "head", "options"]
