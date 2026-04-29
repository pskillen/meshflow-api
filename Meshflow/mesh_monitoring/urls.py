"""URL include target for mesh monitoring."""

from django.urls import include, path

from rest_framework.routers import DefaultRouter

from mesh_monitoring.views import MonitoringAlertsSummaryView, NodeMonitoringConfigView, NodeWatchViewSet

router = DefaultRouter()
router.register(r"watches", NodeWatchViewSet, basename="nodewatch")

urlpatterns = [
    path(
        "nodes/<uuid:observed_node_id>/config/",
        NodeMonitoringConfigView.as_view(),
        name="monitoring-node-config",
    ),
    path(
        "alerts/summary/",
        MonitoringAlertsSummaryView.as_view(),
        name="monitoring-alerts-summary",
    ),
    path("", include(router.urls)),
]
