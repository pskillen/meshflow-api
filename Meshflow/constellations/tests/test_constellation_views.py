from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from constellations.models import Constellation, ConstellationUserMembership, MessageChannel


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
def test_constellation_create_view_django_admin(create_user):
    """Test constellation create view for Django admin."""
    client = APIClient()
    user = create_user(is_staff=True)  # Django admin
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

    # Check that the user is automatically added as an admin
    membership = ConstellationUserMembership.objects.get(user=user, constellation=constellation)
    assert membership.role == "admin"


@pytest.mark.django_db
def test_constellation_create_view_non_admin(create_user):
    """Test constellation create view for non-Django admin."""
    client = APIClient()
    user = create_user(is_staff=False)  # Not a Django admin
    client.force_authenticate(user=user)

    data = {
        "name": "New Constellation",
        "description": "New Description",
    }

    url = reverse("constellation-list")
    response = client.post(url, data)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Constellation.objects.count() == 0


@pytest.mark.django_db
def test_constellation_update_view_admin(create_constellation, create_user):
    """Test constellation update view for constellation admin."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation and make user an admin
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="admin")

    data = {"name": "Updated Constellation", "description": "Updated Description"}

    url = reverse("constellation-detail", kwargs={"pk": constellation.pk})
    response = client.patch(url, data)

    assert response.status_code == status.HTTP_200_OK
    constellation.refresh_from_db()
    assert constellation.name == "Updated Constellation"
    assert constellation.description == "Updated Description"


@pytest.mark.django_db
def test_constellation_update_view_editor(create_constellation, create_user):
    """Test constellation update view for constellation editor."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation and make user an editor
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="editor")

    data = {"name": "Updated Constellation", "description": "Updated Description"}

    url = reverse("constellation-detail", kwargs={"pk": constellation.pk})
    response = client.patch(url, data)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    constellation.refresh_from_db()
    assert constellation.name != "Updated Constellation"


@pytest.mark.django_db
def test_constellation_update_view_viewer(create_constellation, create_user):
    """Test constellation update view for constellation viewer."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation and make user a viewer
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="viewer")

    data = {"name": "Updated Constellation", "description": "Updated Description"}

    url = reverse("constellation-detail", kwargs={"pk": constellation.pk})
    response = client.patch(url, data)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    constellation.refresh_from_db()
    assert constellation.name != "Updated Constellation"


@pytest.mark.django_db
def test_constellation_delete_view_django_admin(create_constellation, create_user):
    """Test constellation delete view for Django admin."""
    client = APIClient()
    user = create_user(is_staff=True)  # Django admin
    client.force_authenticate(user=user)

    constellation = create_constellation()
    url = reverse("constellation-detail", kwargs={"pk": constellation.pk})
    response = client.delete(url)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Constellation.objects.filter(pk=constellation.pk).exists()


@pytest.mark.django_db
def test_constellation_delete_view_constellation_admin(create_constellation, create_user):
    """Test constellation delete view for constellation admin (not Django admin)."""
    client = APIClient()
    user = create_user(is_staff=False)  # Not a Django admin
    client.force_authenticate(user=user)

    # Create constellation and make user an admin
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="admin")

    url = reverse("constellation-detail", kwargs={"pk": constellation.pk})
    response = client.delete(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Constellation.objects.filter(pk=constellation.pk).exists()  # Constellation still exists


@pytest.mark.django_db
def test_constellation_members_view_admin(create_constellation, create_user):
    """Test constellation members management for admin."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation and make user an admin
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="admin")

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

    # Delete a member
    data = {"user": user1.id}
    response = client.delete(url, data, format="json")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    memberships = ConstellationUserMembership.objects.filter(constellation=constellation)
    assert memberships.count() == 2  # Only admin and user2 remain
    assert not ConstellationUserMembership.objects.filter(user=user1, constellation=constellation).exists()


@pytest.mark.django_db
def test_constellation_members_view_editor(create_constellation, create_user):
    """Test constellation members management for editor."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation and make user an editor
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="editor")

    user1 = create_user()

    # Add members
    url = reverse("constellation-members", kwargs={"pk": constellation.pk})
    data = {"members": [{"user": user1.id, "role": "viewer"}]}
    response = client.post(url, data, format="json")

    assert response.status_code == status.HTTP_200_OK
    memberships = ConstellationUserMembership.objects.filter(constellation=constellation)
    assert memberships.count() == 2  # Including the editor user

    user1_membership = memberships.get(user=user1)
    assert user1_membership.role == "viewer"

    # Delete a member
    data = {"user": user1.id}
    response = client.delete(url, data, format="json")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    memberships = ConstellationUserMembership.objects.filter(constellation=constellation)
    assert memberships.count() == 1  # Only editor remains
    assert not ConstellationUserMembership.objects.filter(user=user1, constellation=constellation).exists()


@pytest.mark.django_db
def test_constellation_members_view_viewer(create_constellation, create_user):
    """Test constellation members management for viewer."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation and make user a viewer
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="viewer")

    user1 = create_user()

    # Try to add members
    url = reverse("constellation-members", kwargs={"pk": constellation.pk})
    data = {"members": [{"user": user1.id, "role": "viewer"}]}
    response = client.post(url, data, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    memberships = ConstellationUserMembership.objects.filter(constellation=constellation)
    assert memberships.count() == 1  # Only the viewer user


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


@pytest.mark.django_db
def test_constellation_channels_get_member(create_constellation, create_user):
    """Test GET channels for constellation member."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation and make user a member (viewer)
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="viewer")

    # Create a channel
    channel = MessageChannel.objects.create(name="Test Channel", constellation=constellation)

    url = reverse("constellation-channels", kwargs={"constellation_id": constellation.id})
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]["name"] == channel.name


@pytest.mark.django_db
def test_constellation_channels_get_non_member(create_constellation, create_user):
    """Test GET channels for non-member."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation (user is not a member)
    constellation = create_constellation()

    url = reverse("constellation-channels", kwargs={"constellation_id": constellation.id})
    response = client.get(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_constellation_channels_post_admin(create_constellation, create_user):
    """Test POST channels for constellation admin."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation and make user an admin
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="admin")

    url = reverse("constellation-channels", kwargs={"constellation_id": constellation.id})
    data = {"name": "New Channel"}
    response = client.post(url, data)

    assert response.status_code == status.HTTP_201_CREATED
    assert MessageChannel.objects.count() == 1
    channel = MessageChannel.objects.first()
    assert channel.name == "New Channel"
    assert channel.constellation == constellation


@pytest.mark.django_db
def test_constellation_channels_post_editor(create_constellation, create_user):
    """Test POST channels for constellation editor."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation and make user an editor
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="editor")

    url = reverse("constellation-channels", kwargs={"constellation_id": constellation.id})
    data = {"name": "New Channel"}
    response = client.post(url, data)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert MessageChannel.objects.count() == 0


@pytest.mark.django_db
def test_constellation_channels_put_admin(create_constellation, create_user):
    """Test PUT channels for constellation admin."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation and make user an admin
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="admin")

    # Create a channel
    channel = MessageChannel.objects.create(name="Test Channel", constellation=constellation)

    url = reverse("constellation-channels", kwargs={"constellation_id": constellation.id})
    data = {"id": channel.id, "name": "Updated Channel"}
    response = client.put(url, data)

    assert response.status_code == status.HTTP_200_OK
    channel.refresh_from_db()
    assert channel.name == "Updated Channel"


@pytest.mark.django_db
def test_constellation_channels_delete_admin(create_constellation, create_user):
    """Test DELETE channels for constellation admin."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create constellation and make user an admin
    constellation = create_constellation()
    ConstellationUserMembership.objects.create(user=user, constellation=constellation, role="admin")

    # Create a channel
    channel = MessageChannel.objects.create(name="Test Channel", constellation=constellation)

    url = reverse("constellation-channels", kwargs={"constellation_id": constellation.id})
    data = {"id": channel.id}
    response = client.delete(url, data)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert MessageChannel.objects.count() == 0
