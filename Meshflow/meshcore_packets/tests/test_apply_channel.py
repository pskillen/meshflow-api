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
        "meshcore_packets.services.channel_apply.feeder_ws_group_has_subscribers",
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
                        "region_scope": "sample-west",
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
            "meshcore_packets.services.channel_apply.feeder_ws_group_has_subscribers",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "meshcore_packets.services.channel_apply.dispatch_node_command",
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
            "meshcore_packets.services.channel_apply.feeder_ws_group_has_subscribers",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "meshcore_packets.views.apply_mc_channels_to_feeder",
            return_value="sent",
        ) as dispatch_mock,
    ):
        response = client.post(
            url,
            {
                "channels": [
                    {
                        "mc_channel_idx": 1,
                        "name": "galloway",
                        "mc_channel_type": "HASHTAG",
                    }
                ]
            },
            format="json",
        )

    assert response.status_code == 202
    dispatch_mock.assert_called_once()
    sent_channels = dispatch_mock.call_args[0][1]
    assert sent_channels[0]["name"] == "galloway"
    assert sent_channels[0]["mc_channel_type"] == "HASHTAG"
    assert type(sent_channels[0]["mc_channel_type"]) is str
