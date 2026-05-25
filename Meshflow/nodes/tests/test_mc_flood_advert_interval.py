"""Tests for mc_flood_advert_interval_hours on managed nodes."""

from unittest.mock import patch

from django.urls import reverse

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol


@pytest.mark.django_db
def test_patch_interval_dispatches_refresh(create_user, create_managed_node):
    user = create_user()
    node = create_managed_node(
        owner=user,
        meshtastic_node_id=0,
        protocol=Protocol.MESHCORE,
        mc_flood_advert_interval_hours=6,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("managed-nodes-detail", kwargs={"node_id": node.meshtastic_node_id})

    with patch(
        "meshcore_packets.services.feeder_config.dispatch_feeder_config_refresh",
        return_value="sent",
    ) as mock_dispatch:
        response = client.patch(
            url,
            {"mc_flood_advert_interval_hours": 8},
            format="json",
        )

    assert response.status_code == 200
    assert response.data["mc_flood_advert_interval_hours"] == 8
    mock_dispatch.assert_called_once()
    node.refresh_from_db()
    assert node.mc_flood_advert_interval_hours == 8


@pytest.mark.django_db
def test_patch_same_interval_skips_dispatch(create_user, create_managed_node):
    user = create_user()
    node = create_managed_node(
        owner=user,
        meshtastic_node_id=0,
        protocol=Protocol.MESHCORE,
        mc_flood_advert_interval_hours=6,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("managed-nodes-detail", kwargs={"node_id": node.meshtastic_node_id})

    with patch(
        "meshcore_packets.services.feeder_config.dispatch_feeder_config_refresh",
    ) as mock_dispatch:
        response = client.patch(url, {"name": "renamed"}, format="json")

    assert response.status_code == 200
    mock_dispatch.assert_not_called()


@pytest.mark.django_db
def test_patch_interval_rejected_on_meshtastic(create_user, create_managed_node):
    user = create_user()
    node = create_managed_node(owner=user, protocol=Protocol.MESHTASTIC)
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("managed-nodes-detail", kwargs={"node_id": node.meshtastic_node_id})

    response = client.patch(
        url,
        {"mc_flood_advert_interval_hours": 10},
        format="json",
    )

    assert response.status_code == 400
    assert "mc_flood_advert_interval_hours" in response.data
