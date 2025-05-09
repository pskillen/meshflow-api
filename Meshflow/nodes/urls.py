from django.urls import include, path

from rest_framework.routers import DefaultRouter

from nodes.views import APIKeyViewSet, ManagedNodeViewSet, ObservedNodeClaimView, ObservedNodeViewSet, UserNodeClaimsView

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r"observed-nodes", ObservedNodeViewSet, basename="observed-node")
router.register(r"managed-nodes", ManagedNodeViewSet, basename="managed-nodes")
router.register(r"api-keys", APIKeyViewSet, basename="api-keys")

# The API URLs are now determined automatically by the router
urlpatterns = [
    path("", include(router.urls)),
    path("observed-nodes/<int:node_id>/claim/", ObservedNodeClaimView.as_view(), name="observed-node-claim"),
    path("claims/mine/", UserNodeClaimsView.as_view(), name="user-node-claims"),
]
