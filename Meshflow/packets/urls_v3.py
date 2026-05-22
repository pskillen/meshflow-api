"""URL configuration for feeder API v3 (strict meshtastic_* node upsert wire)."""

from django.urls import include, path

from .views import ManagedNodeBotVersionView, NodeUpsertViewV3, PacketIngestView

urlpatterns = [
    path(
        "<int:node_id>/",
        include(
            [
                path("ingest/", PacketIngestView.as_view(), name="meshtastic-packet-ingest-v3"),
                path("nodes/", NodeUpsertViewV3.as_view(), name="meshtastic-node-upsert-v3"),
                path("bot-version/", ManagedNodeBotVersionView.as_view(), name="meshtastic-bot-version-v3"),
            ]
        ),
    ),
]
