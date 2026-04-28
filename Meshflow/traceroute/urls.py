from django.urls import path

from traceroute_analytics import views as analytics_views

from . import views

app_name = "traceroute"

urlpatterns = [
    path("", views.traceroute_list, name="traceroute-list"),
    path("stats/", analytics_views.traceroute_stats, name="traceroute-stats"),
    path("heatmap-edges/", analytics_views.heatmap_edges, name="traceroute-heatmap-edges"),
    path("feeder-reach/", analytics_views.feeder_reach, name="traceroute-feeder-reach"),
    path("constellation-coverage/", analytics_views.constellation_coverage, name="traceroute-constellation-coverage"),
    path("can_trigger/", views.traceroute_can_trigger, name="traceroute-can-trigger"),
    path("triggerable-nodes/", views.traceroute_triggerable_nodes, name="traceroute-triggerable-nodes"),
    path("trigger/", views.traceroute_trigger, name="traceroute-trigger"),
    path("<int:pk>/", views.traceroute_detail, name="traceroute-detail"),
]
