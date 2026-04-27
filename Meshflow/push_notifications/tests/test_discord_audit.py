"""Tests for Discord DM audit helpers and DiscordNotificationAudit model."""

from unittest.mock import patch

import pytest

from push_notifications.constants import (
    DiscordNotificationFeature,
    DiscordNotificationKind,
    DiscordNotificationStatus,
)
from push_notifications.discord import DiscordSendError
from push_notifications.discord_audit import (
    message_preview,
    record_discord_notification_skip,
    send_discord_dm_with_audit,
)
from push_notifications.models import DiscordNotificationAudit


@pytest.mark.django_db
def test_record_discord_notification_skip_creates_row(create_user):
    user = create_user()
    row = record_discord_notification_skip(
        feature=DiscordNotificationFeature.NODE_WATCH,
        kind=DiscordNotificationKind.NODE_OFFLINE,
        user=user,
        reason="not verified",
        message_preview_text="hello world",
        discord_recipient_id="123",
        related_app_label="nodes",
        related_model_name="ObservedNode",
        related_object_id="99",
        related_context={"k": "v"},
    )
    assert row is not None
    assert row.pk
    assert row.status == DiscordNotificationStatus.SKIPPED
    assert row.reason == "not verified"
    assert row.message_preview == "hello world"
    assert row.discord_recipient_id == "123"
    assert row.related_context == {"k": "v"}
    assert row.attempted_at is None
    assert row.sent_at is None


@pytest.mark.django_db
def test_send_discord_dm_with_audit_sent(create_user):
    user = create_user()
    with patch("push_notifications.discord_audit.send_dm") as send_dm:
        send_discord_dm_with_audit(
            feature=DiscordNotificationFeature.NODE_WATCH,
            kind=DiscordNotificationKind.NODE_OFFLINE,
            user=user,
            discord_user_id="snowflake",
            content="body text",
            related_app_label="nodes",
            related_model_name="ObservedNode",
            related_object_id="1",
            related_context={},
        )
    send_dm.assert_called_once_with("snowflake", "body text")
    row = DiscordNotificationAudit.objects.get()
    assert row.status == DiscordNotificationStatus.SENT
    assert row.message_preview == "body text"
    assert row.discord_recipient_id == "snowflake"
    assert row.attempted_at is not None
    assert row.sent_at is not None


@pytest.mark.django_db
def test_send_discord_dm_with_audit_failed_then_raises(create_user):
    user = create_user()
    with patch("push_notifications.discord_audit.send_dm", side_effect=DiscordSendError("boom")):
        with pytest.raises(DiscordSendError):
            send_discord_dm_with_audit(
                feature=DiscordNotificationFeature.NODE_WATCH,
                kind=DiscordNotificationKind.VERIFICATION_STARTED,
                user=user,
                discord_user_id="x",
                content="c",
            )
    row = DiscordNotificationAudit.objects.get()
    assert row.status == DiscordNotificationStatus.FAILED
    assert "boom" in row.reason


def test_message_preview_truncates():
    long = "a" * 600
    out = message_preview(long, max_len=500)
    assert len(out) == 500
    assert out.endswith("…")


@pytest.mark.django_db
def test_send_discord_dm_with_audit_swallows_audit_db_error_after_send(create_user):
    """Discord DM succeeded; a broken audit insert must not surface to callers."""
    user = create_user()
    mgr = DiscordNotificationAudit.objects
    real_create = mgr.create

    def flaky_create(**kwargs):
        if kwargs.get("status") == DiscordNotificationStatus.SENT:
            raise RuntimeError("db down")
        return real_create(**kwargs)

    with patch("push_notifications.discord_audit.send_dm"):
        with patch.object(mgr, "create", side_effect=flaky_create):
            send_discord_dm_with_audit(
                feature=DiscordNotificationFeature.NODE_WATCH,
                kind=DiscordNotificationKind.NODE_OFFLINE,
                user=user,
                discord_user_id="1",
                content="ok",
            )


@pytest.mark.django_db
def test_record_discord_notification_skip_swallows_db_error(create_user):
    user = create_user()
    with patch.object(DiscordNotificationAudit.objects, "create", side_effect=RuntimeError("db")):
        out = record_discord_notification_skip(
            feature=DiscordNotificationFeature.NODE_WATCH,
            kind=DiscordNotificationKind.NODE_OFFLINE,
            user=user,
            reason="r",
        )
    assert out is None
