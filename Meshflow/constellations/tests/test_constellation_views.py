from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from constellations.models import Constellation, ConstellationUserMembership


@pytest.mark.django_db
def test_constellation_list_view(create_constellation, create_user):
    """Test constellation list view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create some test constellations
    constellation1 = create_constellation(created_by=user)
    constellation2 = create_constellation(created_by=user)

    url = reverse("constellation-list")
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 2
    results = response.data["results"]
    assert len(results) == 2
    assert results[0]["name"] == constellation1.name
    assert results[1]["name"] == constellation2.name


@pytest.mark.django_db
def test_constellation_detail_view(create_constellation, create_user):
    """Test constellation detail view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    constellation = create_constellation(created_by=user)
    url = reverse("constellation-detail", kwargs={"pk": constellation.pk})
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == constellation.name
    assert response.data["description"] == constellation.description


@pytest.mark.django_db
def test_constellation_create_view(create_user):
    """Test constellation create view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    data = {
        "name": "New Constellation",
        "description": "New Description",
    }

    url = reverse("constellation-list")
    response = client.post(url, data)

    assert response.status_code == status.HTTP_201_CREATED
    assert Constellation.objects.count() == 1
    constellation = Constellation.objects.first()
    assert constellation.name == "New Constellation"
    assert constellation.created_by == user


@pytest.mark.django_db
def test_constellation_update_view(create_constellation, create_user):
    """Test constellation update view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    constellation = create_constellation(created_by=user)
    data = {"name": "Updated Constellation", "description": "Updated Description"}

    url = reverse("constellation-detail", kwargs={"pk": constellation.pk})
    response = client.patch(url, data)

    assert response.status_code == status.HTTP_200_OK
    constellation.refresh_from_db()
    assert constellation.name == "Updated Constellation"
    assert constellation.description == "Updated Description"


@pytest.mark.django_db
def test_constellation_delete_view(create_constellation, create_user):
    """Test constellation delete view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    constellation = create_constellation(created_by=user)
    url = reverse("constellation-detail", kwargs={"pk": constellation.pk})
    response = client.delete(url)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Constellation.objects.filter(pk=constellation.pk).exists()


@pytest.mark.django_db
def test_constellation_members_view(create_constellation, create_user):
    """Test constellation members management."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    constellation = create_constellation(created_by=user)
    user1 = create_user()
    user2 = create_user()

    # Add members
    url = reverse("constellation-members", kwargs={"pk": constellation.pk})
    data = {"members": [{"user": user1.id, "role": "viewer"}, {"user": user2.id, "role": "editor"}]}
    response = client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    memberships = ConstellationUserMembership.objects.filter(constellation=constellation)
    assert memberships.count() == 3  # Including the admin user

    user1_membership = memberships.get(user=user1)
    assert user1_membership.role == "viewer"

    user2_membership = memberships.get(user=user2)
    assert user2_membership.role == "editor"

    # Update memberships
    data = {"members": [{"user": user2.id, "role": "viewer"}]}
    response = client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    memberships = ConstellationUserMembership.objects.filter(constellation=constellation)
    assert memberships.count() == 2  # Only admin and user2 remain
    assert not ConstellationUserMembership.objects.filter(user=user1, constellation=constellation).exists()

    user2_membership = memberships.get(user=user2)
    assert user2_membership.role == "viewer"


@pytest.mark.django_db
def test_constellation_permission_unauthorized(create_constellation):
    """Test constellation permissions for unauthorized users."""
    client = APIClient()
    constellation = create_constellation()

    url = reverse("constellation-detail", kwargs={"pk": constellation.pk})
    response = client.get(url)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_constellation_permission_wrong_owner(create_constellation, create_user):
    """Test constellation permissions for wrong owner."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    constellation = create_constellation()  # Created by different user
    url = reverse("constellation-detail", kwargs={"pk": constellation.pk})
    response = client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
