from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model that extends Django's AbstractUser."""

    display_name = models.CharField(max_length=100, blank=True)
    discord_notify_user_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Discord snowflake for DM notifications (set only after verified link).",
    )
    discord_notify_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When Discord identity was last verified for notifications (OAuth link).",
    )

    def __str__(self):
        return self.username
