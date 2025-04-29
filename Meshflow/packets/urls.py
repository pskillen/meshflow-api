"""URL configuration for the packets app."""

from django.urls import include, path

from .views import NodeUpsertView, PacketIngestView

urlpatterns = [
    path(
        "<int:node_id>/",
        include(
            [
                path("ingest/", PacketIngestView.as_view(), name="packet-ingest"),
                path("nodes/", NodeUpsertView.as_view(), name="node-upsert"),
            ]
        ),
    ),
]
