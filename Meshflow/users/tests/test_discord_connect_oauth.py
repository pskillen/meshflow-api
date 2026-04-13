"""Tests for signed Discord connect OAuth state and callback attachment."""

from unittest.mock import patch

from django.core.cache import cache
from django.urls import reverse

import pytest
from allauth.socialaccount.models import SocialAccount

from users.discord_connect_oauth import (
    DiscordAccountAlreadyLinkedError,
    attach_discord_to_user,
    consume_discord_connect_state,
    create_discord_connect_state,
)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_create_and_consume_state_roundtrip(create_user):
    user = create_user()
    state = create_discord_connect_state(user.pk)
    assert isinstance(state, str)
    assert consume_discord_connect_state(state) == user.pk


@pytest.mark.django_db
def test_consume_twice_fails_replay(create_user):
    user = create_user()
    state = create_discord_connect_state(user.pk)
    assert consume_discord_connect_state(state) == user.pk
    with pytest.raises(ValueError, match="nonce_missing"):
        consume_discord_connect_state(state)


def test_tampered_state_fails():
    with pytest.raises(ValueError):
        consume_discord_connect_state("not-a-valid-signature")


@pytest.mark.django_db
def test_attach_discord_to_user_creates_social_account(create_user):
    user = create_user()
    attach_discord_to_user(
        user,
        {
            "id": 123456789012345678,
            "username": "tester",
            "email": "t@example.com",
        },
    )
    sa = SocialAccount.objects.get(user=user, provider="discord")
    assert sa.uid == "123456789012345678"


@pytest.mark.django_db
def test_attach_discord_conflict_other_user(create_user):
    u1 = create_user()
    u2 = create_user()
    attach_discord_to_user(u1, {"id": 999888777666555444, "username": "a"})
    with pytest.raises(DiscordAccountAlreadyLinkedError):
        attach_discord_to_user(u2, {"id": 999888777666555444, "username": "a"})


@pytest.mark.django_db
def test_discord_connect_auth_requires_auth():
    from rest_framework.test import APIClient

    client = APIClient()
    resp = client.get(reverse("discord_connect_auth"))
    assert resp.status_code == 401


@pytest.mark.django_db
def test_discord_connect_auth_returns_authorization_url(create_user):
    from rest_framework.test import APIClient

    user = create_user()
    client = APIClient()
    client.force_authenticate(user=user)
    resp = client.get(reverse("discord_connect_auth"))
    assert resp.status_code == 200
    assert "authorization_url" in resp.data
    assert "discord.com" in resp.data["authorization_url"]
    assert "state=" in resp.data["authorization_url"] or "state%3D" in resp.data["authorization_url"]


@pytest.mark.django_db
def test_discord_connect_callback_success(create_user):
    from rest_framework.test import APIClient

    user = create_user()
    state = create_discord_connect_state(user.pk)

    mock_token = {"access_token": "fake-token"}
    mock_me = {"id": 111222333444555666, "username": "linked", "email": "x@example.com"}

    client = APIClient()
    with patch("users.social_auth.requests.post") as mock_post:
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = mock_token
        with patch("users.discord_connect_oauth.fetch_discord_me", return_value=mock_me):
            resp = client.get(reverse("discord_connect_callback"), {"code": "auth-code", "state": state})
    assert resp.status_code == 302
    assert "token=" in resp["Location"]


@pytest.mark.django_db
def test_discord_connect_callback_invalid_state():
    from rest_framework.test import APIClient

    client = APIClient()
    resp = client.get(reverse("discord_connect_callback"), {"code": "c", "state": "bad"})
    assert resp.status_code == 302
    assert "error=discord_connect_invalid_state" in resp["Location"]
