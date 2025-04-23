from django.contrib.auth import get_user_model

import pytest

User = get_user_model()


@pytest.fixture
def user_data():
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpass123",
        "display_name": "Test User",
    }


@pytest.fixture
def create_user(user_data):
    def make_user(**kwargs):
        data = user_data.copy()
        data.update(kwargs)
        return User.objects.create_user(**data)

    return make_user
