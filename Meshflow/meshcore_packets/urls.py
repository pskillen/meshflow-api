from django.urls import path

from meshcore_packets.views import (
    ManagedNodeMcChannelApplyView,
    MeshCoreFeederBotVersionView,
    MeshCoreMcChannelSyncView,
    MeshCorePacketIngestView,
    MeshCorePacketListView,
)

urlpatterns = [
    path(
        "feeders/<str:feeder_pubkey_prefix>/packets/ingest/",
        MeshCorePacketIngestView.as_view(),
        name="meshcore-feeder-packet-ingest",
    ),
    path(
        "feeders/<str:feeder_pubkey_prefix>/mc-channel-sync/",
        MeshCoreMcChannelSyncView.as_view(),
        name="meshcore-feeder-mc-channel-sync",
    ),
    path(
        "feeders/<str:feeder_pubkey_prefix>/bot-version/",
        MeshCoreFeederBotVersionView.as_view(),
        name="meshcore-feeder-bot-version",
    ),
    path("packets/", MeshCorePacketListView.as_view(), name="meshcore-packet-list"),
    path(
        "managed-nodes/<uuid:internal_id>/apply-mc-channel-config/",
        ManagedNodeMcChannelApplyView.as_view(),
        name="meshcore-apply-mc-channel-config",
    ),
]
