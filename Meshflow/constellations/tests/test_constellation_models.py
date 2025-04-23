import pytest
from constellations.models import Constellation


@pytest.mark.django_db
def test_constellation_creation(create_constellation):
    """Test constellation creation with valid data."""
    constellation = create_constellation()
    assert constellation.name == "Test Constellation"
    assert constellation.description == "Test Description"
    assert constellation.owner is not None


@pytest.mark.django_db
def test_constellation_str_representation(create_constellation):
    """Test constellation string representation."""
    constellation = create_constellation()
    assert str(constellation) == "Test Constellation"


@pytest.mark.django_db
def test_constellation_members(create_constellation, create_user):
    """Test constellation members management."""
    constellation = create_constellation()
    user1 = create_user(username="user1")
    user2 = create_user(username="user2")
    
    # Add members
    constellation.members.add(user1, user2)
    assert constellation.members.count() == 2
    assert user1 in constellation.members.all()
    assert user2 in constellation.members.all()
    
    # Remove member
    constellation.members.remove(user1)
    assert constellation.members.count() == 1
    assert user1 not in constellation.members.all()
    assert user2 in constellation.members.all() 