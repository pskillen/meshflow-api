from django.urls import include, path

from rest_framework.routers import DefaultRouter

from dx_monitoring.views import DxEventViewSet, DxNodeExclusionByNodeIdView, DxNodeExclusionView

router = DefaultRouter()
router.register(r"events", DxEventViewSet, basename="dxevent")

urlpatterns = [
    path("", include(router.urls)),
    path("nodes/exclusion/", DxNodeExclusionView.as_view(), name="dx-node-exclusion"),
    path(
        "nodes/by-node-id/<int:node_id>/exclusion/",
        DxNodeExclusionByNodeIdView.as_view(),
        name="dx-node-exclusion-by-node-id",
    ),
]
