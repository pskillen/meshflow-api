from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .views import ConstellationMembersViewSet, ConstellationMessageChannelsViewSet, ConstellationViewSet

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r"", ConstellationViewSet, basename="constellation")

# The API URLs are now determined automatically by the router
urlpatterns = [
    path("", include(router.urls)),
    path(
        "<int:constellation_id>/members/",
        ConstellationMembersViewSet.as_view({"get": "list", "post": "create"}),
        name="constellation-members-list-create",
    ),
    path(
        "<int:constellation_id>/members/<int:user_id>/",
        ConstellationMembersViewSet.as_view({"put": "update", "delete": "destroy"}),
        name="constellation-members-update-destroy",
    ),
    path(
        "<int:constellation_id>/channels/",
        ConstellationMessageChannelsViewSet.as_view({"get": "list", "post": "create"}),
        name="constellation-channels-list-create",
    ),
    path(
        "<int:constellation_id>/channels/<int:channel_id>/",
        ConstellationMessageChannelsViewSet.as_view({"put": "update", "delete": "destroy"}),
        name="constellation-channels-update-destroy",
    ),
]
