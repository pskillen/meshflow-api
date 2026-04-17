"""HTTP API tests for NodeWatch CRUD."""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

import nodes.tests.conftest  # noqa: F401
from nodes.constants import INFRASTRUCTURE_ROLES
from nodes.models import RoleSource


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_watch_list_requires_auth(api_client):
    r = api_client.get("/api/monitoring/watches/")
    assert r.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_watch_create_requires_auth(api_client, create_observed_node):
    obs = create_observed_node()
    r = api_client.post(
        "/api/monitoring/watches/",
        {"observed_node_id": str(obs.internal_id), "enabled": True},
        format="json",
    )
    assert r.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_watch_crud_claimed_node(api_client, create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(claimed_by=user)
    api_client.force_authenticate(user=user)

    r = api_client.post(
        "/api/monitoring/watches/",
        {"observed_node_id": str(obs.internal_id), "enabled": True},
        format="json",
    )
    assert r.status_code == status.HTTP_201_CREATED
    wid = r.data["id"]
    assert r.data["offline_after"] == 21600
    assert r.data["enabled"] is True
    assert r.data["observed_node"]["node_id_str"] == obs.node_id_str
    assert r.data["observed_node"]["monitoring_verification_started_at"] is None

    r = api_client.patch(
        f"/api/monitoring/nodes/{obs.internal_id}/offline-after/",
        {"offline_after": 90},
        format="json",
    )
    assert r.status_code == status.HTTP_200_OK
    assert r.data["offline_after"] == 90
    assert r.data["editable"] is True

    r = api_client.get(f"/api/monitoring/watches/{wid}/")
    assert r.status_code == status.HTTP_200_OK
    assert r.data["offline_after"] == 90
    assert r.data["observed_node"]["offline_after"] == 90

    r = api_client.get("/api/monitoring/watches/")
    assert r.status_code == status.HTTP_200_OK
    assert r.data["count"] == 1
    assert r.data["results"][0]["id"] == wid

    r = api_client.patch(f"/api/monitoring/watches/{wid}/", {"enabled": False}, format="json")
    assert r.status_code == status.HTTP_200_OK
    assert r.data["enabled"] is False

    r = api_client.delete(f"/api/monitoring/watches/{wid}/")
    assert r.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_monitoring_offline_after_get_editable_flags(api_client, create_user, create_observed_node):
    owner = create_user()
    other = create_user()
    obs = create_observed_node(claimed_by=owner)

    api_client.force_authenticate(user=other)
    r = api_client.get(f"/api/monitoring/nodes/{obs.internal_id}/offline-after/")
    assert r.status_code == status.HTTP_200_OK
    assert r.data["offline_after"] == 21600
    assert r.data["editable"] is False

    api_client.force_authenticate(user=owner)
    r = api_client.get(f"/api/monitoring/nodes/{obs.internal_id}/offline-after/")
    assert r.status_code == status.HTTP_200_OK
    assert r.data["editable"] is True


@pytest.mark.django_db
def test_monitoring_offline_after_patch_forbidden_for_non_owner(api_client, create_user, create_observed_node):
    owner = create_user()
    other = create_user()
    obs = create_observed_node(claimed_by=owner)
    api_client.force_authenticate(user=other)
    r = api_client.patch(
        f"/api/monitoring/nodes/{obs.internal_id}/offline-after/",
        {"offline_after": 120},
        format="json",
    )
    assert r.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_watch_infrastructure_node_any_user(api_client, create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(role=INFRASTRUCTURE_ROLES[0], claimed_by=None)
    api_client.force_authenticate(user=user)
    r = api_client.post(
        "/api/monitoring/watches/",
        {"observed_node_id": str(obs.internal_id)},
        format="json",
    )
    assert r.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_watch_reject_ineligible_node(api_client, create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(role=RoleSource.CLIENT, claimed_by=None)
    api_client.force_authenticate(user=user)
    r = api_client.post(
        "/api/monitoring/watches/",
        {"observed_node_id": str(obs.internal_id)},
        format="json",
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert "observed_node_id" in r.data or "non_field_errors" in r.data


@pytest.mark.django_db
def test_watch_duplicate(api_client, create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(claimed_by=user)
    api_client.force_authenticate(user=user)
    api_client.post(
        "/api/monitoring/watches/",
        {"observed_node_id": str(obs.internal_id)},
        format="json",
    )
    r = api_client.post(
        "/api/monitoring/watches/",
        {"observed_node_id": str(obs.internal_id)},
        format="json",
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_watch_other_user_404(api_client, create_user, create_observed_node):
    from mesh_monitoring.tests.conftest import create_watch_with_offline_threshold

    owner = create_user()
    other = create_user()
    obs = create_observed_node(claimed_by=owner)
    w = create_watch_with_offline_threshold(user=owner, observed_node=obs, offline_after=60)

    api_client.force_authenticate(user=other)
    r = api_client.get(f"/api/monitoring/watches/{w.pk}/")
    assert r.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_watch_presence_hints(api_client, create_user, create_observed_node):
    from django.utils import timezone

    from mesh_monitoring.models import NodePresence

    user = create_user()
    obs = create_observed_node(claimed_by=user)
    now = timezone.now()
    NodePresence.objects.create(
        observed_node=obs,
        verification_started_at=now,
        offline_confirmed_at=None,
    )
    api_client.force_authenticate(user=user)
    r = api_client.post(
        "/api/monitoring/watches/",
        {"observed_node_id": str(obs.internal_id)},
        format="json",
    )
    assert r.status_code == status.HTTP_201_CREATED
    assert r.data["observed_node"]["monitoring_verification_started_at"] is not None
    assert r.data["observed_node"]["node_id"] == obs.node_id
    assert "short_name" in r.data["observed_node"]
