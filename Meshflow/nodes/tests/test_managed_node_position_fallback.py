"""ManagedNode API position falls back to default_location when no observed position."""

from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from nodes.models import NodeLatestStatus


@pytest.mark.django_db
def test_managed_node_position_falls_back_to_default_location(create_managed_node, create_user):
    user = create_user()
    managed = create_managed_node(
        owner=user,
        meshtastic_node_id=123450100,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    list_url = reverse("managed-nodes-list")
    list_resp = client.get(list_url)
    assert list_resp.status_code == status.HTTP_200_OK
    row = next(r for r in list_resp.data["results"] if r["meshtastic_node_id"] == managed.meshtastic_node_id)
    assert row["position"] is not None
    assert row["position"]["latitude"] == 55.95
    assert row["position"]["longitude"] == -3.19

    detail_url = reverse("managed-nodes-detail", kwargs={"node_id": managed.meshtastic_node_id})
    detail_resp = client.get(detail_url)
    assert detail_resp.status_code == status.HTTP_200_OK
    assert detail_resp.data["position"]["latitude"] == 55.95
    assert detail_resp.data["position"]["longitude"] == -3.19


@pytest.mark.django_db
def test_managed_node_position_prefers_observed_over_default(create_managed_node, create_observed_node, create_user):
    user = create_user()
    managed = create_managed_node(
        owner=user,
        meshtastic_node_id=123450101,
        default_location_latitude=55.0,
        default_location_longitude=-4.0,
    )
    observed = create_observed_node(meshtastic_node_id=managed.meshtastic_node_id)
    NodeLatestStatus.objects.create(
        node=observed,
        latitude=56.1,
        longitude=-3.5,
        position_reported_time=None,
    )

    client = APIClient()
    client.force_authenticate(user=user)
    detail_resp = client.get(reverse("managed-nodes-detail", kwargs={"node_id": managed.meshtastic_node_id}))
    assert detail_resp.status_code == status.HTTP_200_OK
    assert detail_resp.data["position"]["latitude"] == 56.1
    assert detail_resp.data["position"]["longitude"] == -3.5


@pytest.mark.django_db
def test_managed_node_position_null_without_observed_or_default(create_managed_node, create_user):
    user = create_user()
    managed = create_managed_node(owner=user, meshtastic_node_id=123450102)

    client = APIClient()
    client.force_authenticate(user=user)
    detail_resp = client.get(reverse("managed-nodes-detail", kwargs={"node_id": managed.meshtastic_node_id}))
    assert detail_resp.status_code == status.HTTP_200_OK
    assert detail_resp.data["position"] is None
