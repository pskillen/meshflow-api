"""REST API for mesh monitoring."""

from django.shortcuts import get_object_or_404

from rest_framework import permissions, status, views, viewsets
from rest_framework.response import Response

from mesh_monitoring.models import NodePresence, NodeWatch
from mesh_monitoring.permission_helpers import user_can_edit_monitoring_offline_after
from mesh_monitoring.serializers import NodePresenceOfflineAfterSerializer, NodeWatchSerializer
from nodes.models import ObservedNode


class NodeMonitoringOfflineAfterView(views.APIView):
    """
    Read or update the node-level silence threshold (NodePresence.offline_after).

    GET/PATCH /api/monitoring/nodes/{observed_node_id}/offline-after/
    observed_node_id is ObservedNode.internal_id (UUID).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, observed_node_id):
        node = get_object_or_404(ObservedNode, pk=observed_node_id)
        presence, _ = NodePresence.objects.get_or_create(
            observed_node=node,
            defaults={"is_offline": False},
        )
        return Response(
            {
                "offline_after": presence.offline_after,
                "editable": user_can_edit_monitoring_offline_after(request.user, node),
            },
        )

    def patch(self, request, observed_node_id):
        node = get_object_or_404(ObservedNode, pk=observed_node_id)
        if not user_can_edit_monitoring_offline_after(request.user, node):
            return Response(status=status.HTTP_403_FORBIDDEN)
        presence, _ = NodePresence.objects.get_or_create(
            observed_node=node,
            defaults={"is_offline": False},
        )
        ser = NodePresenceOfflineAfterSerializer(presence, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(
            {
                "offline_after": ser.instance.offline_after,
                "editable": True,
            },
        )


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
            .select_related("observed_node__claimed_by")
            .select_related("observed_node__mesh_presence")
            .select_related("observed_node__latest_status")
            .order_by("-created_at", "-id")
        )

    def perform_create(self, serializer):
        watch = serializer.save(user=self.request.user)
        NodePresence.objects.get_or_create(
            observed_node=watch.observed_node,
            defaults={"is_offline": False},
        )
