from django.urls import path

from . import views

app_name = "stats"

urlpatterns = [
    path("nodes/<int:node_id>/packets/", views.node_packet_stats, name="node-packet-stats"),
    path("nodes/<int:node_id>/received/", views.node_received_stats, name="node-received-stats"),
    path("global/", views.global_packet_stats, name="global-packet-stats"),
]
