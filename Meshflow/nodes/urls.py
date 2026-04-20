from django.urls import include, path

from rest_framework.routers import DefaultRouter

from nodes.views import (
    APIKeyViewSet,
    DeviceMetricsBulkView,
    EnvironmentMetricsBulkView,
    ManagedNodeViewSet,
    ObservedNodeClaimView,
    ObservedNodeViewSet,
    RfPropagationAssetView,
    UserNodeClaimsView,
)

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r"observed-nodes", ObservedNodeViewSet, basename="observed-node")
router.register(r"managed-nodes", ManagedNodeViewSet, basename="managed-nodes")
router.register(r"api-keys", APIKeyViewSet, basename="api-keys")

# The API URLs are now determined automatically by the router
urlpatterns = [
    path("", include(router.urls)),
    path(
        "device-metrics-bulk/",
        DeviceMetricsBulkView.as_view(),
        name="device-metrics-bulk",
    ),
    path(
        "environment-metrics-bulk/",
        EnvironmentMetricsBulkView.as_view(),
        name="environment-metrics-bulk",
    ),
    path("observed-nodes/<int:node_id>/claim/", ObservedNodeClaimView.as_view(), name="observed-node-claim"),
    path(
        "observed-nodes/<int:node_id>/rf-propagation/asset/<str:filename>",
        RfPropagationAssetView.as_view(),
        name="rf-propagation-asset",
    ),
    path("claims/mine/", UserNodeClaimsView.as_view(), name="user-node-claims"),
]
