"""URL include target for mesh monitoring."""

from django.urls import include, path

from rest_framework.routers import DefaultRouter

from mesh_monitoring.views import NodeWatchViewSet

router = DefaultRouter()
router.register(r"watches", NodeWatchViewSet, basename="nodewatch")

urlpatterns = [
    path("", include(router.urls)),
]
