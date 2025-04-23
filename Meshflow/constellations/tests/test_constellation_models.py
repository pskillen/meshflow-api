import pytest
from constellations.models import Constellation, ConstellationUserMembership


@pytest.mark.django_db
def test_constellation_creation(create_constellation):
    """Test constellation creation with valid data."""
    constellation = create_constellation()
    assert constellation.name == "Test Constellation"
    assert constellation.description == "Test Description"
    assert constellation.created_by is not None


@pytest.mark.django_db
def test_constellation_str_representation(create_constellation):
    """Test constellation string representation."""
    constellation = create_constellation()
    assert str(constellation) == "Test Constellation"


@pytest.mark.django_db
def test_constellation_members(create_constellation, create_user):
    """Test constellation members management."""
    constellation = create_constellation()
    user1 = create_user()
    user2 = create_user()

    # Add members
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

    # Check memberships
    memberships = ConstellationUserMembership.objects.filter(constellation=constellation)
    assert memberships.count() == 3  # one from create_constellation

    # Check specific memberships
    user1_membership = ConstellationUserMembership.objects.get(user=user1, constellation=constellation)
    assert user1_membership.role == "viewer"

    user2_membership = ConstellationUserMembership.objects.get(user=user2, constellation=constellation)
    assert user2_membership.role == "editor"

    # Remove membership
    user1_membership.delete()
    assert ConstellationUserMembership.objects.filter(constellation=constellation).count() == 2
    assert not ConstellationUserMembership.objects.filter(user=user1, constellation=constellation).exists()
    assert ConstellationUserMembership.objects.filter(user=user2, constellation=constellation).exists()
