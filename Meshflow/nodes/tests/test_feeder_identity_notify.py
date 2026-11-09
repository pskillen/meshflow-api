"""Owner Discord DM for a feeder number change (ID-4): nodes.services.feeder_identity_notify."""

from unittest.mock import patch

import pytest

import nodes.tests.conftest  # noqa: F401
from common.meshtastic_identity import normalise_pubkey
from nodes.models import ManagedNodeIdentityEvent
from nodes.services.feeder_identity import apply_reported_identity, repoint_feeder
from nodes.services.feeder_identity_notify import notify_owner
from push_notifications.constants import DiscordNotificationFeature, DiscordNotificationKind, DiscordNotificationStatus
from push_notifications.discord import DiscordSendError
from push_notifications.models import DiscordNotificationAudit

Outcome = ManagedNodeIdentityEvent.Outcome
Reason = ManagedNodeIdentityEvent.Reason

OLD_NUM = 0xDA545C78
NEW_NUM = 0x4396524C
KEY_B64 = "oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs="

VERIFIED = "nodes.services.feeder_identity_notify.user_has_verified_discord_dm_target"
SEND_DM = "push_notifications.discord_audit.send_dm"


@pytest.fixture
def feeder(create_managed_node):
    return create_managed_node(
        meshtastic_node_id=OLD_NUM, name="Hill", meshtastic_public_key=normalise_pubkey(KEY_B64)
    )


def _event(feeder, outcome, reason=None):
    return ManagedNodeIdentityEvent.objects.create(
        managed_node=feeder,
        old_meshtastic_node_id=OLD_NUM,
        new_meshtastic_node_id=NEW_NUM,
        reported_public_key=normalise_pubkey(KEY_B64),
        outcome=outcome,
        reason=reason,
    )


@pytest.mark.django_db
def test_auto_updated_sends_dm_with_audit(feeder):
    event = _event(feeder, Outcome.AUTO_UPDATED)
    with patch(VERIFIED, return_value=True), patch(SEND_DM) as send_dm:
        assert notify_owner(event) is True
    send_dm.assert_called_once()
    text = send_dm.call_args.args[1] if len(send_dm.call_args.args) > 1 else send_dm.call_args.kwargs.get("content")
    assert text == (
        "Your feeder Hill changed node number: !da545c78 is now !4396524c. "
        "It keeps its history and API key. Nothing to do."
    )
    row = DiscordNotificationAudit.objects.get()
    assert row.status == DiscordNotificationStatus.SENT
    assert row.feature == DiscordNotificationFeature.FEEDER_IDENTITY
    assert row.kind == DiscordNotificationKind.FEEDER_IDENTITY_CHANGED
    assert row.user_id == feeder.owner_id


@pytest.mark.django_db
def test_flagged_sends_dm_with_reason(feeder):
    event = _event(feeder, Outcome.FLAGGED, Reason.NUMBER_COLLISION)
    with patch(VERIFIED, return_value=True), patch(SEND_DM) as send_dm:
        assert notify_owner(event) is True
    send_dm.assert_called_once()
    row = DiscordNotificationAudit.objects.get()
    assert row.kind == DiscordNotificationKind.FEEDER_IDENTITY_FLAGGED
    assert "reported node number !4396524c but is stored as !da545c78" in row.message_preview
    assert "another feeder already has that number" in row.message_preview
    assert "Open My Nodes to review it." in row.message_preview


@pytest.mark.django_db
def test_auto_rekey_disabled_reason_text(feeder):
    event = _event(feeder, Outcome.FLAGGED, Reason.AUTO_REKEY_DISABLED)
    with patch(VERIFIED, return_value=True), patch(SEND_DM):
        notify_owner(event)
    assert "automatic updates are off on this server" in DiscordNotificationAudit.objects.get().message_preview


@pytest.mark.django_db
@pytest.mark.parametrize("outcome", [Outcome.MANUAL, Outcome.KEY_CHANGED])
def test_manual_and_key_changed_are_not_sent(feeder, outcome):
    event = _event(feeder, outcome)
    with patch(VERIFIED, return_value=True), patch(SEND_DM) as send_dm:
        assert notify_owner(event) is False
    send_dm.assert_not_called()
    assert DiscordNotificationAudit.objects.count() == 0


@pytest.mark.django_db
def test_missing_discord_target_writes_skip_audit(feeder):
    event = _event(feeder, Outcome.AUTO_UPDATED)
    with patch(VERIFIED, return_value=False), patch(SEND_DM) as send_dm:
        assert notify_owner(event) is False
    send_dm.assert_not_called()
    row = DiscordNotificationAudit.objects.get()
    assert row.status == DiscordNotificationStatus.SKIPPED
    assert row.kind == DiscordNotificationKind.FEEDER_IDENTITY_CHANGED


@pytest.mark.django_db
def test_discord_send_error_does_not_propagate(feeder):
    event = _event(feeder, Outcome.AUTO_UPDATED)
    with patch(VERIFIED, return_value=True), patch(SEND_DM, side_effect=DiscordSendError("boom")):
        assert notify_owner(event) is False
    assert DiscordNotificationAudit.objects.get().status == DiscordNotificationStatus.FAILED


@pytest.mark.django_db
def test_unexpected_error_does_not_propagate(feeder):
    event = _event(feeder, Outcome.AUTO_UPDATED)
    with patch(VERIFIED, side_effect=RuntimeError("boom")):
        assert notify_owner(event) is False


@pytest.mark.django_db
def test_auto_rekey_sends_dm_through_receiver(feeder, settings):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    with patch(VERIFIED, return_value=True), patch(SEND_DM) as send_dm:
        event = apply_reported_identity(feeder, reported_node_num=NEW_NUM, reported_pubkey=KEY_B64)
    assert event.outcome == Outcome.AUTO_UPDATED
    send_dm.assert_called_once()
    assert DiscordNotificationAudit.objects.get().kind == DiscordNotificationKind.FEEDER_IDENTITY_CHANGED


@pytest.mark.django_db
def test_flagged_rekey_sends_dm_once(feeder, settings):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False
    with patch(VERIFIED, return_value=True), patch(SEND_DM) as send_dm:
        first = apply_reported_identity(feeder, reported_node_num=NEW_NUM, reported_pubkey=KEY_B64)
        second = apply_reported_identity(feeder, reported_node_num=NEW_NUM, reported_pubkey=KEY_B64)
    assert first.outcome == Outcome.FLAGGED
    assert second is None
    send_dm.assert_called_once()
    assert DiscordNotificationAudit.objects.get().kind == DiscordNotificationKind.FEEDER_IDENTITY_FLAGGED


@pytest.mark.django_db
def test_failing_dm_leaves_rekey_applied(feeder, settings):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    with patch(VERIFIED, return_value=True), patch(SEND_DM, side_effect=DiscordSendError("boom")):
        event = apply_reported_identity(feeder, reported_node_num=NEW_NUM, reported_pubkey=KEY_B64)
    feeder.refresh_from_db()
    assert event.outcome == Outcome.AUTO_UPDATED
    assert feeder.meshtastic_node_id == NEW_NUM


@pytest.mark.django_db
def test_manual_repoint_sends_no_dm(feeder, create_user):
    staff = create_user(is_staff=True)
    with patch(VERIFIED, return_value=True), patch(SEND_DM) as send_dm:
        event = repoint_feeder(feeder, NEW_NUM, actor=staff)
    assert event.outcome == Outcome.MANUAL
    send_dm.assert_not_called()
    assert DiscordNotificationAudit.objects.count() == 0
