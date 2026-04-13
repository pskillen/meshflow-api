"""Serializers for Discord notification prefs API."""

from rest_framework import serializers


class DiscordNotificationPrefsSerializer(serializers.Serializer):
    """Read/update shape for GET / PATCH discord notification prefs."""

    discord_linked = serializers.BooleanField(read_only=True)
    discord_notify_verified = serializers.BooleanField(read_only=True)
