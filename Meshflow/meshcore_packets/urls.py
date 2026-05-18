from django.urls import path

from meshcore_packets.views import MeshCorePacketIngestView, MeshCorePacketListView

urlpatterns = [
    path("packets/ingest/", MeshCorePacketIngestView.as_view(), name="meshcore-packet-ingest"),
    path("packets/", MeshCorePacketListView.as_view(), name="meshcore-packet-list"),
]
