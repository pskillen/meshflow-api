"""Representative guest / user / feeder access tests for issue #346."""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from common.access import grant_feeder_role
from constellations.models import Constellation


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def constellation(db, create_user):
    user = create_user()
    return Constellation.objects.create(name="Public Test", description="", created_by=user)


@pytest.mark.django_db
class TestGuestReadAccess:
    def test_guest_can_list_constellations(self, api_client, constellation):
        response = api_client.get("/api/constellations/")
        assert response.status_code == status.HTTP_200_OK
        ids = [c["id"] for c in response.data["results"]]
        assert constellation.id in ids

    def test_guest_observed_node_hides_position(self, api_client, observed_node_with_position):
        response = api_client.get(f"/api/nodes/observed-nodes/{observed_node_with_position.internal_id}/")
        assert response.status_code == status.HTTP_200_OK
        assert "latest_position" not in response.data or response.data.get("latest_position") is None
        assert "owner" not in response.data

    def test_authenticated_user_sees_position(self, api_client, create_user, observed_node_with_position):
        user = create_user()
        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/nodes/observed-nodes/{observed_node_with_position.internal_id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data.get("latest_position") is not None


@pytest.mark.django_db
class TestFeederApiKeys:
    def test_plain_user_cannot_create_api_key(self, api_client, create_user, constellation):
        api_client.force_authenticate(user=create_user())
        response = api_client.post(
            "/api/nodes/api-keys/",
            {"name": "test", "constellation": constellation.id},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_feeder_can_create_api_key_any_constellation(self, api_client, create_user, constellation):
        user = create_user()
        grant_feeder_role(user)
        api_client.force_authenticate(user=user)
        response = api_client.post(
            "/api/nodes/api-keys/",
            {"name": "feeder-key", "constellation": constellation.id},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
