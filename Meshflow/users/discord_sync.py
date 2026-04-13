"""Keep User Discord notification fields in sync with django-allauth SocialAccount."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

from allauth.socialaccount.models import SocialAccount

User = get_user_model()


def sync_discord_notify_from_social_accounts(user: User) -> bool:
    """
    If the user has a linked Discord SocialAccount, copy uid to discord_notify_user_id
    and set discord_notify_verified_at. Returns True if a Discord account was found.
    """
    try:
        sa = SocialAccount.objects.get(user=user, provider="discord")
    except SocialAccount.DoesNotExist:
        return False

    User.objects.filter(pk=user.pk).update(
        discord_notify_user_id=sa.uid,
        discord_notify_verified_at=timezone.now(),
    )
    return True


def user_has_verified_discord_dm_target(user: User) -> bool:
    """True only if User fields match an existing Discord SocialAccount (anti-spam)."""
    if not user.discord_notify_user_id or not user.discord_notify_verified_at:
        return False
    return SocialAccount.objects.filter(
        user=user,
        provider="discord",
        uid=user.discord_notify_user_id,
    ).exists()


def clear_discord_notify_fields(user_id: int) -> None:
    User.objects.filter(pk=user_id).update(
        discord_notify_user_id="",
        discord_notify_verified_at=None,
    )
