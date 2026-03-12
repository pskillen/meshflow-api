from django.urls import path

from . import views

app_name = "traceroute"

urlpatterns = [
    path("", views.traceroute_list, name="traceroute-list"),
    path("can_trigger/", views.traceroute_can_trigger, name="traceroute-can-trigger"),
    path("trigger/", views.traceroute_trigger, name="traceroute-trigger"),
    path("<int:pk>/", views.traceroute_detail, name="traceroute-detail"),
]
