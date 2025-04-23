import pytest
from constellations.serializers import ConstellationSerializer


@pytest.mark.django_db
def test_constellation_serializer_valid_data(create_constellation):
    """Test ConstellationSerializer with valid data."""
    constellation = create_constellation()
    serializer = ConstellationSerializer(constellation)

    data = serializer.data
    assert data["name"] == "Test Constellation"
    assert data["description"] == "Test Description"
    assert "owner" in data
    assert "members" in data


@pytest.mark.django_db
def test_constellation_serializer_create(create_user):
    """Test ConstellationSerializer create method."""
    user = create_user()
    data = {
        "name": "New Constellation",
        "description": "New Description",
        "owner": user.id
    }
    serializer = ConstellationSerializer(data=data)
    assert serializer.is_valid()
    constellation = serializer.save()

    assert constellation.name == "New Constellation"
    assert constellation.description == "New Description"
    assert constellation.owner == user


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
    assert updated_constellation.owner == constellation.owner


@pytest.mark.django_db
def test_constellation_serializer_members(create_constellation, create_user):
    """Test ConstellationSerializer members field."""
    constellation = create_constellation()
    user1 = create_user(username="user1")
    user2 = create_user(username="user2")
    
    constellation.members.add(user1, user2)
    serializer = ConstellationSerializer(constellation)
    
    data = serializer.data
    assert len(data["members"]) == 2
    assert any(member["username"] == "user1" for member in data["members"])
    assert any(member["username"] == "user2" for member in data["members"])


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