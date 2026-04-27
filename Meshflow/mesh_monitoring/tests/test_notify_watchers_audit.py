"""DiscordNotificationAudit rows from node-watch notify paths."""

from unittest.mock import patch

import pytest

import nodes.tests.conftest  # noqa: F401
from common.mesh_node_helpers import meshtastic_id_to_hex
from mesh_monitoring.services import notify_watchers_node_offline, notify_watchers_verification_started
from mesh_monitoring.tests.conftest import create_watch_with_offline_threshold
from nodes.models import RoleSource
from push_notifications.constants import DiscordNotificationKind, DiscordNotificationStatus
from push_notifications.models import DiscordNotificationAudit


@pytest.mark.django_db
def test_offline_notify_writes_sent_audit(create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(
        node_id=0x10101010,
        node_id_str=meshtastic_id_to_hex(0x10101010),
        long_name="N",
        short_name="SN",
        claimed_by=user,
    )
    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)
    with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
        with patch("push_notifications.discord_audit.send_dm"):
            notify_watchers_node_offline(obs)
    row = DiscordNotificationAudit.objects.get()
    assert row.status == DiscordNotificationStatus.SENT
    assert row.kind == DiscordNotificationKind.NODE_OFFLINE


@pytest.mark.django_db
def test_offline_notify_writes_skipped_audit_when_discord_unverified(create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(
        node_id=0x20202020,
        node_id_str=meshtastic_id_to_hex(0x20202020),
        claimed_by=user,
    )
    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)
    with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=False):
        with patch("push_notifications.discord_audit.send_dm") as send_dm:
            attempted = notify_watchers_node_offline(obs)
    send_dm.assert_not_called()
    assert attempted == 0
    row = DiscordNotificationAudit.objects.get()
    assert row.status == DiscordNotificationStatus.SKIPPED


@pytest.mark.django_db
def test_offline_notify_writes_failed_audit_on_discord_error(create_user, create_observed_node):
    from push_notifications.discord import DiscordSendError

    user = create_user()
    obs = create_observed_node(
        node_id=0x30303030,
        node_id_str=meshtastic_id_to_hex(0x30303030),
        claimed_by=user,
    )
    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)
    with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
        with patch(
            "push_notifications.discord_audit.send_dm",
            side_effect=DiscordSendError("HTTP 500"),
        ):
            notify_watchers_node_offline(obs)
    row = DiscordNotificationAudit.objects.get()
    assert row.status == DiscordNotificationStatus.FAILED
    assert "HTTP 500" in row.reason


@pytest.mark.django_db
def test_verification_started_writes_sent_and_skipped_audits(create_user, create_observed_node):
    u_send = create_user(username="watcher_send")
    u_skip = create_user(username="watcher_skip")
    obs = create_observed_node(
        node_id=0x40404040,
        node_id_str=meshtastic_id_to_hex(0x40404040),
        role=RoleSource.ROUTER,
    )
    create_watch_with_offline_threshold(user=u_send, observed_node=obs, offline_after=60)
    create_watch_with_offline_threshold(user=u_skip, observed_node=obs, offline_after=60)

    def verified(u):
        return u.username == "watcher_send"

    with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", side_effect=verified):
        with patch("push_notifications.discord_audit.send_dm"):
            notify_watchers_verification_started(obs, silence_threshold_seconds=42)

    kinds = {r.user_id: r for r in DiscordNotificationAudit.objects.all()}
    assert kinds[u_send.pk].status == DiscordNotificationStatus.SENT
    assert kinds[u_send.pk].kind == DiscordNotificationKind.VERIFICATION_STARTED
    assert kinds[u_skip.pk].status == DiscordNotificationStatus.SKIPPED
    assert kinds[u_skip.pk].related_context.get("silence_threshold_seconds") == 42
