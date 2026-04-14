"""Tests for Discord notification prefs and test DM API."""

from unittest.mock import MagicMock, patch

from django.test import override_settings
from django.urls import reverse

import pytest
from allauth.socialaccount.models import SocialAccount
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_discord_prefs_get_not_linked(create_user):
    user = create_user()
    client = APIClient()
    client.force_authenticate(user=user)
    resp = client.get(reverse("discord-notification-prefs"))
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["discord_linked"] is False
    assert resp.data["discord_notify_verified"] is False


@pytest.mark.django_db
def test_discord_prefs_get_verified_after_sync(create_user):
    user = create_user()
    SocialAccount.objects.create(
        user=user,
        provider="discord",
        uid="987654321098765432",
        extra_data={},
    )
    from users.discord_sync import sync_discord_notify_from_social_accounts

    assert sync_discord_notify_from_social_accounts(user) is True
    user.refresh_from_db()
    assert user.discord_notify_user_id == "987654321098765432"
    assert user.discord_notify_verified_at is not None

    client = APIClient()
    client.force_authenticate(user=user)
    resp = client.get(reverse("discord-notification-prefs"))
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["discord_linked"] is True
    assert resp.data["discord_notify_verified"] is True


@pytest.mark.django_db
def test_discord_prefs_patch_resyncs(create_user):
    user = create_user()
    SocialAccount.objects.create(
        user=user,
        provider="discord",
        uid="111",
        extra_data={},
    )
    client = APIClient()
    client.force_authenticate(user=user)
    resp = client.patch(reverse("discord-notification-prefs"), {}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["discord_notify_verified"] is True
    user.refresh_from_db()
    assert user.discord_notify_user_id == "111"


@pytest.mark.django_db
def test_discord_test_requires_verified(create_user):
    user = create_user()
    user.discord_notify_user_id = "999"
    user.save(update_fields=["discord_notify_user_id"])
    client = APIClient()
    client.force_authenticate(user=user)
    resp = client.post(reverse("discord-notification-test"))
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
@override_settings(DISCORD_BOT_TOKEN="fake.bot.token")
def test_discord_test_ok_when_verified(create_user):
    user = create_user()
    SocialAccount.objects.create(
        user=user,
        provider="discord",
        uid="555444333222111000",
        extra_data={},
    )
    from users.discord_sync import sync_discord_notify_from_social_accounts

    sync_discord_notify_from_social_accounts(user)

    mock_channel = MagicMock()
    mock_channel.ok = True
    mock_channel.json.return_value = {"id": "dm-channel-1"}
    mock_msg = MagicMock()
    mock_msg.ok = True

    with patch("push_notifications.discord.requests.post", side_effect=[mock_channel, mock_msg]):
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.post(reverse("discord-notification-test"))

    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_clear_discord_notify_on_social_removed(create_user):
    user = create_user()
    sa = SocialAccount.objects.create(
        user=user,
        provider="discord",
        uid="888",
        extra_data={},
    )
    from users.discord_sync import sync_discord_notify_from_social_accounts

    sync_discord_notify_from_social_accounts(user)
    user.refresh_from_db()
    assert user.discord_notify_user_id == "888"

    from allauth.socialaccount.signals import social_account_removed

    social_account_removed.send(sender=None, request=None, socialaccount=sa)
    user.refresh_from_db()
    assert user.discord_notify_user_id == ""
    assert user.discord_notify_verified_at is None
