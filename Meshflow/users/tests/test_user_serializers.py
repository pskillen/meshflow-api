import pytest

from users.serializers import UserSerializer


@pytest.mark.django_db
def test_user_serializer_valid_data(create_user):
    """Test UserSerializer with valid data."""
    user = create_user()
    serializer = UserSerializer(user)

    data = serializer.data
    assert data["id"] == user.id
    assert data["username"] == user.username
    assert data["email"] == user.email
    assert data["display_name"] == "Test User"


@pytest.mark.django_db
def test_user_serializer_create():
    """Test UserSerializer create method."""
    data = {
        "username": "newuser",
        "email": "new@example.com",
        "display_name": "New User",
        "password": "newpass123",
    }
    serializer = UserSerializer(data=data)
    assert serializer.is_valid()
    user = serializer.save()

    assert user.username == "newuser"
    assert user.email == "new@example.com"
    assert user.display_name == "New User"
    assert user.check_password("newpass123")


@pytest.mark.django_db
def test_user_serializer_update(create_user):
    """Test UserSerializer update method."""
    user = create_user()
    data = {"display_name": "Updated Name"}
    serializer = UserSerializer(user, data=data, partial=True)
    assert serializer.is_valid()
    updated_user = serializer.save()

    assert updated_user.display_name == "Updated Name"
    assert updated_user.username == user.username  # Should not change


@pytest.mark.django_db
def test_user_serializer_invalid_data():
    """Test UserSerializer with invalid data."""
    data = {
        "username": "",  # Invalid: empty username
        "email": "invalid-email",
        "display_name": "Test User",
    }
    serializer = UserSerializer(data=data)
    assert not serializer.is_valid()
    assert "username" in serializer.errors
    assert "email" in serializer.errors
