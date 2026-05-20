from django.urls import path

from meshcore_packets.views import (
    ManagedNodeMcChannelApplyView,
    MeshCoreMcChannelSyncView,
    MeshCorePacketIngestView,
    MeshCorePacketListView,
)

urlpatterns = [
    path("packets/ingest/", MeshCorePacketIngestView.as_view(), name="meshcore-packet-ingest"),
    path("packets/", MeshCorePacketListView.as_view(), name="meshcore-packet-list"),
    path("feeder/mc-channel-sync/", MeshCoreMcChannelSyncView.as_view(), name="meshcore-mc-channel-sync"),
    path(
        "managed-nodes/<uuid:internal_id>/apply-mc-channel-config/",
        ManagedNodeMcChannelApplyView.as_view(),
        name="meshcore-apply-mc-channel-config",
    ),
]
