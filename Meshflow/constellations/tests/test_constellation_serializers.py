import pytest
from rest_framework.test import APIRequestFactory
from constellations.serializers import ConstellationSerializer
from constellations.models import ConstellationUserMembership


@pytest.mark.django_db
def test_constellation_serializer_valid_data(create_constellation):
    """Test ConstellationSerializer with valid data."""
    constellation = create_constellation()
    serializer = ConstellationSerializer(constellation)

    data = serializer.data
    assert data["name"] == "Test Constellation"
    assert data["description"] == "Test Description"
    assert "created_by" in data


@pytest.mark.django_db
def test_constellation_serializer_create(create_user):
    """Test ConstellationSerializer create method."""
    user = create_user()
    factory = APIRequestFactory()
    request = factory.post('/api/constellations/')
    request.user = user

    data = {
        "name": "New Constellation",
        "description": "New Description",
    }
    serializer = ConstellationSerializer(data=data, context={'request': request})
    assert serializer.is_valid()
    constellation = serializer.save()

    assert constellation.name == "New Constellation"
    assert constellation.description == "New Description"
    assert constellation.created_by == user


@pytest.mark.django_db
def test_constellation_serializer_update(create_constellation):
    """Test ConstellationSerializer update method."""
    constellation = create_constellation()
    data = {
        "name": "Updated Constellation",
        "description": "Updated Description"
    }
    serializer = ConstellationSerializer(constellation, data=data, partial=True)
    assert serializer.is_valid()
    updated_constellation = serializer.save()

    assert updated_constellation.name == "Updated Constellation"
    assert updated_constellation.description == "Updated Description"
    assert updated_constellation.created_by == constellation.created_by


@pytest.mark.django_db
def test_constellation_serializer_members(create_constellation, create_user):
    """Test ConstellationSerializer members field."""
    constellation = create_constellation()
    user1 = create_user()
    user2 = create_user()

    # Add members through ConstellationUserMembership
    ConstellationUserMembership.objects.create(
        user=user1,
        constellation=constellation,
        role="viewer"
    )
    ConstellationUserMembership.objects.create(
        user=user2,
        constellation=constellation,
        role="editor"
    )

    # Refresh the constellation instance to get the latest data
    constellation.refresh_from_db()

    serializer = ConstellationSerializer(constellation)
    data = serializer.data

    # Check memberships through the serializer
    assert "members" in data
    assert len(data["members"]) == 3  # one from create_constellation
    member_usernames = [member["username"] for member in data["members"]]
    assert user1.username in member_usernames
    assert user2.username in member_usernames


@pytest.mark.django_db
def test_constellation_serializer_invalid_data():
    """Test ConstellationSerializer with invalid data."""
    data = {
        "name": "",  # Invalid: empty name
        "description": "Test Description",
    }
    serializer = ConstellationSerializer(data=data)
    assert not serializer.is_valid()
    assert "name" in serializer.errors
