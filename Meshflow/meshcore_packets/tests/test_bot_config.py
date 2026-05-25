"""Tests for feeder bot-config GET."""

import pytest
from rest_framework.test import APIClient

from meshcore_packets.tests.conftest import FEEDER_MC_PUBKEY_PREFIX, feeder_url


@pytest.mark.django_db
def test_bot_config_returns_interval(meshcore_feeder):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=meshcore_feeder["api_key"].key)
    url = feeder_url("meshcore-feeder-bot-config", FEEDER_MC_PUBKEY_PREFIX)

    response = client.get(url)

    assert response.status_code == 200
    assert response.data["mc_flood_advert_interval_hours"] == 6


@pytest.mark.django_db
def test_bot_config_reflects_managed_node_value(meshcore_feeder):
    node = meshcore_feeder["node"]
    node.mc_flood_advert_interval_hours = 12
    node.save(update_fields=["mc_flood_advert_interval_hours"])

    client = APIClient()
    client.credentials(HTTP_X_API_KEY=meshcore_feeder["api_key"].key)
    url = feeder_url("meshcore-feeder-bot-config", FEEDER_MC_PUBKEY_PREFIX)

    response = client.get(url)

    assert response.status_code == 200
    assert response.data["mc_flood_advert_interval_hours"] == 12


@pytest.mark.django_db
def test_bot_config_wrong_prefix_403(meshcore_feeder):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=meshcore_feeder["api_key"].key)
    url = feeder_url("meshcore-feeder-bot-config", "deadbeef0000")

    response = client.get(url)

    assert response.status_code == 403
