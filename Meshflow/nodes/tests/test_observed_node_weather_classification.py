from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import EnvironmentExposure, NodeLatestStatus, WeatherUse


@pytest.mark.django_db
def test_observed_node_detail_includes_weather_fields(create_observed_node, create_user):
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)
    node = create_observed_node(
        node_id=100100100,
        node_id_str=meshtastic_id_to_hex(100100100),
        weather_use=WeatherUse.INCLUDE,
        environment_exposure=EnvironmentExposure.OUTDOOR,
    )
    response = client.get(reverse("observed-node-detail", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["environment_exposure"] == "outdoor"
    assert response.data["weather_use"] == "include"
    assert response.data["environment_settings_editable"] is False


@pytest.mark.django_db
def test_environment_settings_editable_for_claim_owner(create_observed_node, create_user):
    owner = create_user()
    node = create_observed_node(
        node_id=200200200,
        node_id_str=meshtastic_id_to_hex(200200200),
        claimed_by=owner,
    )
    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.get(reverse("observed-node-detail", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["environment_settings_editable"] is True


@pytest.mark.django_db
def test_environment_settings_editable_for_staff(create_observed_node, create_user):
    staff = create_user(is_staff=True)
    node = create_observed_node(
        node_id=300300300,
        node_id_str=meshtastic_id_to_hex(300300300),
    )
    client = APIClient()
    client.force_authenticate(user=staff)
    response = client.get(reverse("observed-node-detail", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["environment_settings_editable"] is True


@pytest.mark.django_db
def test_environment_settings_patch_claim_owner(create_observed_node, create_user):
    owner = create_user()
    node = create_observed_node(
        node_id=400400400,
        node_id_str=meshtastic_id_to_hex(400400400),
        claimed_by=owner,
    )
    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("observed-node-environment-settings", kwargs={"node_id": node.node_id})
    response = client.patch(
        url,
        {"environment_exposure": "indoor", "weather_use": "exclude"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["environment_exposure"] == "indoor"
    assert response.data["weather_use"] == "exclude"
    node.refresh_from_db()
    assert node.environment_exposure == EnvironmentExposure.INDOOR
    assert node.weather_use == WeatherUse.EXCLUDE


@pytest.mark.django_db
def test_environment_settings_patch_staff(create_observed_node, create_user):
    staff = create_user(is_staff=True)
    node = create_observed_node(
        node_id=500500500,
        node_id_str=meshtastic_id_to_hex(500500500),
    )
    client = APIClient()
    client.force_authenticate(user=staff)
    url = reverse("observed-node-environment-settings", kwargs={"node_id": node.node_id})
    response = client.patch(url, {"weather_use": "include"}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["weather_use"] == "include"


@pytest.mark.django_db
def test_environment_settings_patch_forbidden(create_observed_node, create_user):
    owner = create_user()
    other = create_user()
    node = create_observed_node(
        node_id=600600600,
        node_id_str=meshtastic_id_to_hex(600600600),
        claimed_by=owner,
    )
    client = APIClient()
    client.force_authenticate(user=other)
    url = reverse("observed-node-environment-settings", kwargs={"node_id": node.node_id})
    response = client.patch(url, {"weather_use": "exclude"}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_environment_settings_patch_empty_body(create_observed_node, create_user):
    staff = create_user(is_staff=True)
    node = create_observed_node(
        node_id=700700700,
        node_id_str=meshtastic_id_to_hex(700700700),
    )
    client = APIClient()
    client.force_authenticate(user=staff)
    url = reverse("observed-node-environment-settings", kwargs={"node_id": node.node_id})
    response = client.patch(url, {}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_weather_list_filter_weather_use(create_observed_node, create_user):
    user = create_user()
    now = timezone.now()

    def make_with_env(node_id, wu):
        n = create_observed_node(
            node_id=node_id,
            node_id_str=meshtastic_id_to_hex(node_id),
            weather_use=wu,
        )
        NodeLatestStatus.objects.update_or_create(
            node=n,
            defaults={
                "environment_reported_time": now,
                "environment_temperature": 12.0,
            },
        )
        return n

    make_with_env(800800801, WeatherUse.INCLUDE)
    make_with_env(800800802, WeatherUse.EXCLUDE)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(
        reverse("observed-node-weather"),
        {"weather_use": "include"},
    )
    assert response.status_code == status.HTTP_200_OK
    ids = {r["node_id"] for r in response.data["results"]}
    assert 800800801 in ids
    assert 800800802 not in ids


@pytest.mark.django_db
def test_weather_list_invalid_weather_use_returns_400(create_observed_node, create_user):
    user = create_user()
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(
        reverse("observed-node-weather"),
        {"weather_use": "not-a-real-value"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
