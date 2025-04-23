import uuid

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

_usernames = []


def get_username():
    username = f"testuser_{len(_usernames)}"
    _usernames.append(username)
    return username


def generate_user_data():
    unique_id = str(uuid.uuid4())[:8]  # Use first 8 chars of a UUID
    username = f"testuser_{unique_id}"
    return {
        "username": username,
        "email": f"{username}@example.com",
        "password": "testpass123",
        "display_name": "Test User",
    }


@pytest.fixture
def user_data():
    return generate_user_data()


@pytest.fixture
def create_user():
    def make_user(**kwargs):
        data = generate_user_data()
        data.update(kwargs)
        return User.objects.create_user(**data)

    return make_user
