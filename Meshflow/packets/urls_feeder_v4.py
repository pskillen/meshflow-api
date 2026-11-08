"""URL configuration for the v4 feeder API (``/api/v4/feeder/``; key-scoped, no node number in the path)."""

from django.urls import path

from .views_feeder_v4 import (
    FeederBotVersionViewV4,
    FeederIdentityView,
    FeederMeshtasticIngestViewV4,
    FeederMeshtasticNodeUpsertViewV4,
)

urlpatterns = [
    path("identity/", FeederIdentityView.as_view(), name="feeder-v4-identity"),
    path("bot-version/", FeederBotVersionViewV4.as_view(), name="feeder-v4-bot-version"),
    path("meshtastic/ingest/", FeederMeshtasticIngestViewV4.as_view(), name="feeder-v4-meshtastic-ingest"),
    path("meshtastic/nodes/", FeederMeshtasticNodeUpsertViewV4.as_view(), name="feeder-v4-meshtastic-nodes"),
]
