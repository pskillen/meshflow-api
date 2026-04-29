"""REST API for mesh monitoring."""

from django.shortcuts import get_object_or_404

from rest_framework import permissions, status, views, viewsets
from rest_framework.response import Response

from mesh_monitoring.models import NodeMonitoringConfig, NodePresence, NodeWatch
from mesh_monitoring.permission_helpers import user_can_edit_node_monitoring_config
from mesh_monitoring.serializers import NodeMonitoringConfigSerializer, NodeWatchSerializer
from mesh_monitoring.summary import mesh_infra_monitoring_alert_counts
from nodes.models import ObservedNode


class NodeMonitoringConfigView(views.APIView):
    """
    Read or update per-node monitoring configuration (silence threshold + battery alerts).

    GET/PATCH /api/monitoring/nodes/{observed_node_id}/config/
    observed_node_id is ObservedNode.internal_id (UUID).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, observed_node_id):
        node = get_object_or_404(ObservedNode, pk=observed_node_id)
        NodePresence.objects.get_or_create(
            observed_node=node,
            defaults={"is_offline": False},
        )
        cfg, _ = NodeMonitoringConfig.objects.get_or_create(
            observed_node=node,
            defaults={"last_heard_offline_after_seconds": 21600},
        )
        ser = NodeMonitoringConfigSerializer(cfg, context={"request": request})
        return Response(ser.data)

    def patch(self, request, observed_node_id):
        node = get_object_or_404(ObservedNode, pk=observed_node_id)
        if not user_can_edit_node_monitoring_config(request.user, node):
            return Response(status=status.HTTP_403_FORBIDDEN)
        NodePresence.objects.get_or_create(
            observed_node=node,
            defaults={"is_offline": False},
        )
        cfg, _ = NodeMonitoringConfig.objects.get_or_create(
            observed_node=node,
            defaults={"last_heard_offline_after_seconds": 21600},
        )
        ser = NodeMonitoringConfigSerializer(cfg, data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(NodeMonitoringConfigSerializer(cfg, context={"request": request}).data)


class MonitoringAlertsSummaryView(views.APIView):
    """
    GET /api/monitoring/alerts/summary/?scope=mesh_infra

    Operational counts for mesh infrastructure alerting (not filtered by the current user's Discord opt-ins).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        scope = request.query_params.get("scope", "").strip()
        if scope != "mesh_infra":
            return Response(
                {"detail": "Unsupported scope. Use ?scope=mesh_infra."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"mesh_infra": mesh_infra_monitoring_alert_counts()})


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
            .select_related("observed_node__monitoring_config")
            .select_related("observed_node__latest_status")
            .order_by("-created_at", "-id")
        )

    def perform_create(self, serializer):
        watch = serializer.save(user=self.request.user)
        NodePresence.objects.get_or_create(
            observed_node=watch.observed_node,
            defaults={"is_offline": False},
        )
        NodeMonitoringConfig.objects.get_or_create(
            observed_node=watch.observed_node,
            defaults={"last_heard_offline_after_seconds": 21600},
        )
