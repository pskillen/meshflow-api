from django.urls import path

from . import views

app_name = "traceroute"

urlpatterns = [
    path("", views.traceroute_list, name="traceroute-list"),
    path("stats/", views.traceroute_stats, name="traceroute-stats"),
    path("heatmap-edges/", views.heatmap_edges, name="traceroute-heatmap-edges"),
    path("feeder-ranges/", views.feeder_ranges, name="traceroute-feeder-ranges"),
    path("can_trigger/", views.traceroute_can_trigger, name="traceroute-can-trigger"),
    path("triggerable-nodes/", views.traceroute_triggerable_nodes, name="traceroute-triggerable-nodes"),
    path("trigger/", views.traceroute_trigger, name="traceroute-trigger"),
    path("<int:pk>/", views.traceroute_detail, name="traceroute-detail"),
]
