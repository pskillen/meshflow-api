"""API views for Discord DM notification settings and test."""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from push_notifications.discord import DiscordSendError, send_dm
from users.discord_sync import sync_discord_notify_from_social_accounts, user_has_verified_discord_dm_target
from users.serializers_discord import DiscordNotificationPrefsSerializer

logger = logging.getLogger(__name__)

User = get_user_model()

TEST_MESSAGE = "Meshflow test notification: Discord DM delivery is working."


class DiscordNotificationPrefsView(APIView):
    """
    GET: linked + verified status for Discord notifications.
    PATCH: re-sync discord_notify_* from the user's linked Discord SocialAccount (OAuth).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = User.objects.get(pk=request.user.pk)
        serializer = DiscordNotificationPrefsSerializer(
            {
                "discord_linked": _discord_linked(user),
                "discord_notify_verified": user_has_verified_discord_dm_target(user),
            }
        )
        return Response(serializer.data)

    def patch(self, request):
        user = User.objects.get(pk=request.user.pk)
        sync_discord_notify_from_social_accounts(user)
        user.refresh_from_db()
        serializer = DiscordNotificationPrefsSerializer(
            {
                "discord_linked": _discord_linked(user),
                "discord_notify_verified": user_has_verified_discord_dm_target(user),
            }
        )
        return Response(serializer.data)


class DiscordTestNotificationView(APIView):
    """POST: send a test DM to the verified Discord user id (requires bot token)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = User.objects.get(pk=request.user.pk)
        if not user_has_verified_discord_dm_target(user):
            return Response(
                {"detail": "Discord notifications are not verified. Link Discord via OAuth first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            send_dm(user.discord_notify_user_id, TEST_MESSAGE)
        except DiscordSendError as e:
            logger.warning("Discord test DM failed for user_id=%s: %s", user.pk, e)
            return Response(
                {"detail": "Could not send Discord message. Check DISCORD_BOT_TOKEN and bot permissions."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "ok"}, status=status.HTTP_200_OK)


def _discord_linked(user: User) -> bool:
    from allauth.socialaccount.models import SocialAccount

    return SocialAccount.objects.filter(user=user, provider="discord").exists()
