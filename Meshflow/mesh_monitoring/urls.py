"""URL include target for mesh monitoring."""

from django.urls import include, path

from rest_framework.routers import DefaultRouter

from mesh_monitoring.views import NodeMonitoringOfflineAfterView, NodeWatchViewSet

router = DefaultRouter()
router.register(r"watches", NodeWatchViewSet, basename="nodewatch")

urlpatterns = [
    path(
        "nodes/<uuid:observed_node_id>/offline-after/",
        NodeMonitoringOfflineAfterView.as_view(),
        name="monitoring-node-offline-after",
    ),
    path("", include(router.urls)),
]
