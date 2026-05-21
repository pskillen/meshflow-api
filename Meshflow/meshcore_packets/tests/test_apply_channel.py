"""Tests for apply-mc-channel-config API."""

from unittest.mock import AsyncMock, patch

from django.urls import reverse

import pytest
from rest_framework.test import APIClient

from common.feeder_ws import COMMAND_DISPATCH_UNAVAILABLE, FEEDER_BOT_NOT_CONNECTED
from common.protocol import Protocol


@pytest.mark.django_db
def test_apply_returns_503_when_feeder_not_connected(create_user, create_managed_node):
    user = create_user()
    node = create_managed_node(
        owner=user,
        meshtastic_node_id=0,
        protocol=Protocol.MESHCORE,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("meshcore-apply-mc-channel-config", kwargs={"internal_id": node.internal_id})

    with patch(
        "meshcore_packets.views.feeder_ws_group_has_subscribers",
        new_callable=AsyncMock,
        return_value=False,
    ):
        response = client.post(
            url,
            {
                "channels": [
                    {
                        "mc_channel_idx": 0,
                        "name": "galloway",
                        "mc_channel_type": "HASHTAG",
                        "mc_hashtag": "galloway",
                    }
                ]
            },
            format="json",
        )

    assert response.status_code == 503
    assert response.data["code"] == FEEDER_BOT_NOT_CONNECTED
    assert "not connected" in response.data["detail"].lower()


@pytest.mark.django_db
def test_apply_returns_503_when_dispatch_fails(create_user, create_managed_node):
    user = create_user()
    node = create_managed_node(
        owner=user,
        meshtastic_node_id=0,
        protocol=Protocol.MESHCORE,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("meshcore-apply-mc-channel-config", kwargs={"internal_id": node.internal_id})

    with (
        patch(
            "meshcore_packets.views.feeder_ws_group_has_subscribers",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "meshcore_packets.views.dispatch_node_command",
            new_callable=AsyncMock,
            side_effect=RuntimeError("TCPTransport closed"),
        ),
    ):
        response = client.post(
            url,
            {
                "channels": [
                    {
                        "mc_channel_idx": 0,
                        "name": "Public",
                        "mc_channel_type": "PUBLIC",
                    }
                ]
            },
            format="json",
        )

    assert response.status_code == 503
    assert response.data["code"] == COMMAND_DISPATCH_UNAVAILABLE


@pytest.mark.django_db
def test_apply_dispatches_when_feeder_connected(create_user, create_managed_node):
    user = create_user()
    node = create_managed_node(
        owner=user,
        meshtastic_node_id=0,
        protocol=Protocol.MESHCORE,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("meshcore-apply-mc-channel-config", kwargs={"internal_id": node.internal_id})

    with (
        patch(
            "meshcore_packets.views.feeder_ws_group_has_subscribers",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "meshcore_packets.views.dispatch_node_command",
            new_callable=AsyncMock,
        ) as dispatch_mock,
    ):
        response = client.post(
            url,
            {
                "channels": [
                    {
                        "mc_channel_idx": 1,
                        "name": "tag",
                        "mc_channel_type": "HASHTAG",
                        "mc_hashtag": "#galloway",
                    }
                ]
            },
            format="json",
        )

    assert response.status_code == 202
    dispatch_mock.assert_awaited_once()
    sent_channels = dispatch_mock.await_args[0][1]["channels"]
    assert sent_channels[0]["mc_hashtag"] == "galloway"
    assert sent_channels[0]["name"] == "galloway"
