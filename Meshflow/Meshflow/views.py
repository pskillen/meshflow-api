"""Views for the Meshflow app."""

from django.conf import settings

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class StatusView(APIView):
    """
    Return basic status information including the version.

    This endpoint is public and doesn't require authentication.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "version": settings.VERSION})
