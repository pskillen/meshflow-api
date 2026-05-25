"""Tests for NodeClaimConsumer WebSocket."""

import json

from django.test import override_settings

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

import Meshflow.routing  # noqa: F401

application = URLRouter(Meshflow.routing.websocket_urlpatterns)


@pytest.mark.django_db
@pytest.mark.asyncio
@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
async def test_node_claim_consumer_receives_accepted_event(create_user):
    user = await database_sync_to_async(create_user)()
    token = AccessToken.for_user(user)
    url = f"/ws/claims/?token={str(token)}"

    communicator = WebsocketCommunicator(application, url)
    connected, _ = await communicator.connect()
    assert connected is True

    channel_layer = get_channel_layer()
    from common.ws_groups import user_claims_ws_group

    await channel_layer.group_send(
        user_claims_ws_group(user.id),
        {
            "type": "node_claim_update",
            "payload": {
                "event": "node_claim_accepted",
                "node_internal_id": "00000000-0000-0000-0000-000000000001",
                "node_id_str": "mc:aabbccddeeff",
                "protocol": 2,
                "accepted_at": "2026-05-25T12:00:00+00:00",
            },
        },
    )

    response = await communicator.receive_from()
    data = json.loads(response)
    assert data["event"] == "node_claim_accepted"
    assert data["node_id_str"] == "mc:aabbccddeeff"

    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_node_claim_consumer_rejects_anonymous():
    communicator = WebsocketCommunicator(application, "/ws/claims/")
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()
