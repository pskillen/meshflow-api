"""Signal handlers for users app."""

from django.contrib.auth import get_user_model
from django.dispatch import receiver

from allauth.socialaccount.signals import social_account_added, social_account_removed, social_account_updated

from users import discord_sync

User = get_user_model()


@receiver(social_account_added, dispatch_uid="users_sync_discord_notify_on_added")
@receiver(social_account_updated, dispatch_uid="users_sync_discord_notify_on_updated")
def sync_discord_notify_on_social_account_change(sender, request, sociallogin, **kwargs):
    account = sociallogin.account
    if account.provider != "discord":
        return
    user = sociallogin.user
    if not user.pk:
        return
    discord_sync.sync_discord_notify_from_social_accounts(user)


@receiver(social_account_removed, dispatch_uid="users_clear_discord_notify_on_removed")
def clear_discord_notify_on_social_account_removed(sender, request, socialaccount, **kwargs):
    if socialaccount.provider != "discord":
        return
    discord_sync.clear_discord_notify_fields(socialaccount.user_id)
