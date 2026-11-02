from django.urls import path

from .views_data import (
    ConstellationsView,
    InfraNodesView,
    MeshCoreInfraNodesView,
    MeshCoreSummaryView,
    MeshCoreTimeseriesView,
    MetaView,
    SummaryView,
    TimeseriesView,
)
from .views_keys import KeyAcceptTermsView, KeyDetailView, KeyListCreateView, KeyRevokeView, TermsView, WithdrawView

urlpatterns = [
    path("terms/", TermsView.as_view(), name="m2m-terms"),
    path("keys/", KeyListCreateView.as_view(), name="m2m-keys"),
    path("keys/<uuid:key_id>/", KeyDetailView.as_view(), name="m2m-key-detail"),
    path("keys/<uuid:key_id>/revoke/", KeyRevokeView.as_view(), name="m2m-key-revoke"),
    path("keys/<uuid:key_id>/accept-terms/", KeyAcceptTermsView.as_view(), name="m2m-key-accept-terms"),
    path("admin/users/<int:user_id>/withdraw/", WithdrawView.as_view(), name="m2m-withdraw"),
    path("v1/meta", MetaView.as_view(), name="m2m-meta"),
    path("v1/constellations", ConstellationsView.as_view(), name="m2m-constellations"),
    path("v1/meshtastic/summary", SummaryView.as_view(), name="m2m-mt-summary"),
    path("v1/meshtastic/timeseries", TimeseriesView.as_view(), name="m2m-mt-timeseries"),
    path("v1/meshtastic/infra-nodes", InfraNodesView.as_view(), name="m2m-mt-infra"),
    path("v1/meshcore/summary", MeshCoreSummaryView.as_view(), name="m2m-mc-summary"),
    path("v1/meshcore/timeseries", MeshCoreTimeseriesView.as_view(), name="m2m-mc-timeseries"),
    path("v1/meshcore/infra-nodes", MeshCoreInfraNodesView.as_view(), name="m2m-mc-infra"),
]
