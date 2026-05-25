from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .views import ConstellationMessageChannelsViewSet, ConstellationViewSet

router = DefaultRouter()
router.register(r"", ConstellationViewSet, basename="constellation")

urlpatterns = [
    path("", include(router.urls)),
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
