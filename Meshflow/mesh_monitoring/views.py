"""REST API for mesh monitoring."""

from rest_framework import permissions, viewsets

from mesh_monitoring.models import NodeWatch
from mesh_monitoring.serializers import NodeWatchSerializer


class NodeWatchViewSet(viewsets.ModelViewSet):
    """
    CRUD for the current user's NodeWatch rows.

    List/create: GET/POST /api/monitoring/watches/
    Detail: GET/PATCH/PUT/DELETE /api/monitoring/watches/{id}/
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NodeWatchSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return (
            NodeWatch.objects.filter(user=self.request.user)
            .select_related("observed_node")
            .select_related("observed_node__mesh_presence")
            .order_by("-created_at", "-id")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
