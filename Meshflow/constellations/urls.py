from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .views import ConstellationMemberListView, ConstellationMessageChannelListCreateView, ConstellationViewSet

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r"", ConstellationViewSet, basename="constellation")

# The API URLs are now determined automatically by the router
urlpatterns = [
    path("", include(router.urls)),
    path(
        "<int:constellation_id>/channels",
        ConstellationMessageChannelListCreateView.as_view(),
        name="constellation-channels",
    ),
    path("<int:constellation_id>/members", ConstellationMemberListView.as_view(), name="constellation-members"),
]
