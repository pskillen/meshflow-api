"""URL configuration for the packets app."""

from django.urls import include, path

from .views import ManagedNodeBotVersionView, NodeUpsertView, PacketIngestView

urlpatterns = [
    path(
        "<int:node_id>/",
        include(
            [
                path("ingest/", PacketIngestView.as_view(), name="meshtastic-packet-ingest"),
                path("nodes/", NodeUpsertView.as_view(), name="meshtastic-node-upsert"),
                path("bot-version/", ManagedNodeBotVersionView.as_view(), name="meshtastic-bot-version"),
            ]
        ),
    ),
]
