from django.urls import path

from meshcore_packet_path.views import (
    PathTracingEdgesListView,
    PathTracingSegmentDetailView,
    PathTracingSegmentListView,
)

urlpatterns = [
    path("edges/", PathTracingEdgesListView.as_view(), name="meshcore-path-tracing-edges"),
    path("segments/", PathTracingSegmentListView.as_view(), name="meshcore-path-tracing-segments"),
    path(
        "segments/<uuid:pk>/",
        PathTracingSegmentDetailView.as_view(),
        name="meshcore-path-tracing-segment-detail",
    ),
]
