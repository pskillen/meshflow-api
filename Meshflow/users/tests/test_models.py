import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_create_user(create_user):
    """Test creating a user with valid data."""
    user = create_user()
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.display_name == "Test User"
    assert user.check_password("testpass123")
    assert not user.is_staff
    assert not user.is_superuser


@pytest.mark.django_db
def test_create_superuser(create_user):
    """Test creating a superuser."""
    superuser = create_user(is_staff=True, is_superuser=True)
    assert superuser.is_staff
    assert superuser.is_superuser


@pytest.mark.django_db
def test_user_str_method(create_user):
    """Test the string representation of a user."""
    user = create_user()
    assert str(user) == "testuser"


@pytest.mark.django_db
def test_user_display_name_optional(create_user):
    """Test that display_name is optional."""
    user = create_user(display_name="")
    assert user.display_name == ""
