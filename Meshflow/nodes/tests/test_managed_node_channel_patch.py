"""Tests for managed node channel mapping updates (PATCH) and permissions."""

from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from constellations.models import MessageChannel


@pytest.mark.django_db
def test_managed_node_patch_channels_owner_success(create_user, create_constellation, create_managed_node):
    owner = create_user()
    constellation = create_constellation(created_by=owner)
    other_constellation = create_constellation()
    ch_ok = MessageChannel.objects.create(name="map-me", constellation=constellation)
    MessageChannel.objects.create(name="other", constellation=other_constellation)

    node = create_managed_node(
        owner=owner,
        constellation=constellation,
        channel_0=None,
        channel_1=None,
    )

    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("managed-nodes-detail", kwargs={"node_id": node.node_id})

    response = client.patch(url, {"channel_0": ch_ok.id}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["channel_0"] == {"id": ch_ok.id, "name": ch_ok.name}

    node.refresh_from_db()
    assert node.channel_0_id == ch_ok.id


@pytest.mark.django_db
def test_managed_node_patch_channel_wrong_constellation_returns_400(
    create_user, create_constellation, create_managed_node
):
    owner = create_user()
    constellation = create_constellation(created_by=owner)
    other_constellation = create_constellation()
    ch_wrong = MessageChannel.objects.create(name="foreign", constellation=other_constellation)

    node = create_managed_node(
        owner=owner,
        constellation=constellation,
        channel_0=None,
        channel_1=None,
    )

    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("managed-nodes-detail", kwargs={"node_id": node.node_id})

    response = client.patch(url, {"channel_0": ch_wrong.id}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "channel_0" in response.data


@pytest.mark.django_db
def test_managed_node_patch_channels_non_owner_forbidden(create_user, create_constellation, create_managed_node):
    owner = create_user()
    other = create_user()
    constellation = create_constellation(created_by=owner)
    ch = MessageChannel.objects.create(name="ok", constellation=constellation)

    node = create_managed_node(
        owner=owner,
        constellation=constellation,
        channel_0=None,
        channel_1=None,
    )

    client = APIClient()
    client.force_authenticate(user=other)
    url = reverse("managed-nodes-detail", kwargs={"node_id": node.node_id})

    response = client.patch(url, {"channel_0": ch.id}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_managed_node_retrieve_owner_includes_channels(create_user, create_constellation, create_managed_node):
    owner = create_user()
    constellation = create_constellation(created_by=owner)
    ch = MessageChannel.objects.create(name="primary", constellation=constellation)

    node = create_managed_node(
        owner=owner,
        constellation=constellation,
        channel_0=ch,
        channel_1=None,
    )

    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("managed-nodes-detail", kwargs={"node_id": node.node_id})

    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["channel_0"] == {"id": ch.id, "name": ch.name}


@pytest.mark.django_db
def test_managed_node_retrieve_non_owner_omits_channels(create_user, create_constellation, create_managed_node):
    owner = create_user()
    viewer = create_user()
    constellation = create_constellation(created_by=owner)
    ch = MessageChannel.objects.create(name="primary", constellation=constellation)

    node = create_managed_node(
        owner=owner,
        constellation=constellation,
        channel_0=ch,
        channel_1=None,
    )

    client = APIClient()
    client.force_authenticate(user=viewer)
    url = reverse("managed-nodes-detail", kwargs={"node_id": node.node_id})

    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert "channel_0" not in response.data
