"""Mesh monitoring pauses offline checks on a replaced number and tells watchers once."""

from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
from mesh_monitoring.models import NodePresence, NodeWatch
from mesh_monitoring.tasks import process_node_watch_presence, update_learned_offline_thresholds
from mesh_monitoring.tests.conftest import create_watch_with_offline_threshold
from nodes.models import ObservedNodeIdentityLink
from push_notifications.constants import DiscordNotificationKind, DiscordNotificationStatus
from push_notifications.discord import DiscordSendError
from push_notifications.models import DiscordNotificationAudit

Link = ObservedNodeIdentityLink


def _link(old, new, state=Link.State.AUTO):
    return Link.objects.create(
        old_node=old,
        new_node=new,
        evidence=Link.Evidence.PUBLIC_KEY,
        confidence=Link.Confidence.STRONG,
        state=state,
    )


def _heard(node, ago: timedelta):
    node.last_heard = timezone.now() - ago
    node.save(update_fields=["last_heard"])


@pytest.fixture
def verified():
    with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
        yield


@pytest.fixture
def replaced_pair(create_user, create_observed_node):
    """A watched old row silent for an hour (threshold 60 s) whose successor was heard just now."""
    user = create_user()
    old = create_observed_node(meshtastic_node_id=0x11110001, long_name="Old", short_name="OLD", claimed_by=user)
    new = create_observed_node(meshtastic_node_id=0x11110002, long_name="New", short_name="NEW")
    _heard(old, timedelta(hours=1))
    _heard(new, timedelta(seconds=5))
    create_watch_with_offline_threshold(user=user, observed_node=old, offline_after=60)
    link = _link(old, new)
    return user, old, new, link


@pytest.mark.django_db
def test_replaced_row_is_paused(replaced_pair, verified):
    _, old, _, _ = replaced_pair
    with patch("push_notifications.discord_audit.send_dm"):
        with patch("mesh_monitoring.tasks._dispatch_monitoring_round") as dispatch:
            result = process_node_watch_presence()
    dispatch.assert_not_called()
    assert result == {"watched": 0, "replaced": 1}
    presence = NodePresence.objects.get(observed_node=old)
    assert presence.verification_started_at is None
    assert presence.offline_confirmed_at is None
    assert presence.is_offline is False
    assert not DiscordNotificationAudit.objects.filter(kind=DiscordNotificationKind.NODE_OFFLINE).exists()


@pytest.mark.django_db
def test_replaced_row_keeps_confirmed_offline_presence(replaced_pair, verified):
    _, old, _, _ = replaced_pair
    at = timezone.now() - timedelta(minutes=30)
    NodePresence.objects.filter(observed_node=old).update(is_offline=True, offline_confirmed_at=at)
    with patch("push_notifications.discord_audit.send_dm"):
        process_node_watch_presence()
    presence = NodePresence.objects.get(observed_node=old)
    assert presence.is_offline is True
    assert presence.offline_confirmed_at == at


@pytest.mark.django_db
def test_old_heard_after_successor_is_processed_as_today(replaced_pair, verified):
    _, old, new, _ = replaced_pair
    _heard(new, timedelta(hours=2))
    _heard(old, timedelta(hours=1))  # old number heard after the successor: not replaced
    with patch("mesh_monitoring.tasks._dispatch_monitoring_round"):
        result = process_node_watch_presence()
    assert result == {"watched": 1, "replaced": 0}
    assert NodePresence.objects.get(observed_node=old).verification_started_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize("state", [Link.State.SUGGESTED, Link.State.REJECTED])
def test_non_live_link_is_processed_as_today(replaced_pair, verified, state):
    _, old, _, link = replaced_pair
    Link.objects.filter(pk=link.pk).update(state=state)
    with patch("mesh_monitoring.tasks._dispatch_monitoring_round"):
        result = process_node_watch_presence()
    assert result == {"watched": 1, "replaced": 0}
    assert NodePresence.objects.get(observed_node=old).verification_started_at is not None


@pytest.mark.django_db
def test_learned_thresholds_skip_replaced_rows(replaced_pair):
    _, old, _, _ = replaced_pair
    with patch("mesh_monitoring.tasks.node_gaps", return_value=[]) as gaps:
        result = update_learned_offline_thresholds()
    gaps.assert_not_called()
    assert result == {"updated": 0, "failed": 0}
    assert NodePresence.objects.get(observed_node=old).learned_offline_computed_at is None


@pytest.mark.django_db
def test_query_count_does_not_grow_per_unreplaced_row(create_user, create_observed_node):
    user = create_user()

    def make(n):
        for i in range(n):
            node = create_observed_node(meshtastic_node_id=0x22220000 + i + 100 * n, claimed_by=user)
            _heard(node, timedelta(seconds=1))  # not silent: no verification work
            create_watch_with_offline_threshold(user=user, observed_node=node, offline_after=3600)

    make(2)
    with CaptureQueriesContext(connection) as small:
        process_node_watch_presence()
    make(6)
    with CaptureQueriesContext(connection) as large:
        process_node_watch_presence()
    # Per-row work is the same as before this change; the split adds a constant number of queries.
    per_row = (len(large) - len(small)) / 6
    assert per_row <= (len(small) - 3) / 2 + 1


@pytest.mark.django_db
def test_first_run_dms_watcher_once_and_marks_link(replaced_pair, verified):
    user, old, new, link = replaced_pair
    with patch("push_notifications.discord_audit.send_dm") as send_dm:
        process_node_watch_presence()
        process_node_watch_presence()
    assert send_dm.call_count == 1
    row = DiscordNotificationAudit.objects.get(kind=DiscordNotificationKind.NODE_REPLACED)
    assert row.status == DiscordNotificationStatus.SENT
    assert row.related_object_id == str(old.pk)
    assert new.node_id_str in row.message_preview
    link.refresh_from_db()
    assert link.detail["watchers_notified"]["sent"] == 1


@pytest.mark.django_db
def test_replaced_but_old_heard_inside_threshold_sends_no_dm(replaced_pair, verified):
    _, old, _, link = replaced_pair
    _heard(old, timedelta(seconds=30))  # threshold 60 s, successor heard 5 s ago
    with patch("push_notifications.discord_audit.send_dm") as send_dm:
        result = process_node_watch_presence()
    assert result["replaced"] == 1
    send_dm.assert_not_called()
    link.refresh_from_db()
    assert "watchers_notified" not in link.detail


@pytest.mark.django_db
def test_dm_fires_once_when_old_goes_silent_past_threshold(replaced_pair, verified):
    _, old, _, link = replaced_pair
    _heard(old, timedelta(seconds=30))
    with patch("push_notifications.discord_audit.send_dm") as send_dm:
        process_node_watch_presence()
        send_dm.assert_not_called()
        _heard(old, timedelta(seconds=120))  # now silent past its 60 s threshold, still replaced
        process_node_watch_presence()
        process_node_watch_presence()
    assert send_dm.call_count == 1
    link.refresh_from_db()
    assert link.detail["watchers_notified"]["sent"] == 1


@pytest.mark.django_db
def test_spoof_old_heard_again_before_threshold_never_dms(replaced_pair, verified):
    _, old, new, link = replaced_pair
    _heard(old, timedelta(seconds=30))
    _heard(new, timedelta(seconds=5))
    with patch("push_notifications.discord_audit.send_dm") as send_dm:
        process_node_watch_presence()
        _heard(old, timedelta(seconds=1))  # the real radio transmits again: newer than the spoofed row
        result = process_node_watch_presence()
    assert result["replaced"] == 0  # no longer replaced, processed as today
    send_dm.assert_not_called()
    assert not DiscordNotificationAudit.objects.filter(kind=DiscordNotificationKind.NODE_REPLACED).exists()
    link.refresh_from_db()
    assert "watchers_notified" not in link.detail


@pytest.mark.django_db
def test_two_watchers_two_dms(replaced_pair, create_user, verified):
    _, old, _, _ = replaced_pair
    NodeWatch.objects.bulk_create([NodeWatch(user=create_user(username="second"), observed_node=old)])  # skips clean()
    with patch("push_notifications.discord_audit.send_dm") as send_dm:
        process_node_watch_presence()
    assert send_dm.call_count == 2


@pytest.mark.django_db
def test_stale_old_row_marked_and_quiet(replaced_pair, verified):
    _, old, _, link = replaced_pair
    _heard(old, timedelta(days=8))
    with patch("push_notifications.discord_audit.send_dm") as send_dm:
        process_node_watch_presence()
    send_dm.assert_not_called()
    assert not DiscordNotificationAudit.objects.exists()
    link.refresh_from_db()
    assert link.detail["watchers_notified"]["skipped"] == "stale"


@pytest.mark.django_db
def test_unverified_watcher_gets_skip_audit(replaced_pair):
    _, _, _, link = replaced_pair
    with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=False):
        with patch("push_notifications.discord_audit.send_dm") as send_dm:
            process_node_watch_presence()
    send_dm.assert_not_called()
    row = DiscordNotificationAudit.objects.get(kind=DiscordNotificationKind.NODE_REPLACED)
    assert row.status == DiscordNotificationStatus.SKIPPED
    link.refresh_from_db()
    assert link.detail["watchers_notified"]["sent"] == 0


@pytest.mark.django_db
def test_chain_names_newest_identity(create_user, create_observed_node, verified):
    user = create_user()
    a = create_observed_node(meshtastic_node_id=0x33330001, claimed_by=user)
    b = create_observed_node(meshtastic_node_id=0x33330002)
    c = create_observed_node(meshtastic_node_id=0x33330003)
    _heard(a, timedelta(hours=3))
    _heard(b, timedelta(hours=2))
    _heard(c, timedelta(seconds=5))
    create_watch_with_offline_threshold(user=user, observed_node=a, offline_after=60)
    _link(a, b)
    _link(b, c)
    with patch("push_notifications.discord_audit.send_dm"):
        process_node_watch_presence()
    row = DiscordNotificationAudit.objects.get(kind=DiscordNotificationKind.NODE_REPLACED)
    assert c.node_id_str in row.message_preview
    assert b.node_id_str not in row.message_preview.split("now uses node")[1]


@pytest.mark.django_db
def test_raising_send_keeps_mark_and_task_finishes(replaced_pair, verified):
    _, _, _, link = replaced_pair
    with patch("push_notifications.discord_audit.send_dm", side_effect=DiscordSendError("HTTP 500")):
        result = process_node_watch_presence()
    assert result["replaced"] == 1
    link.refresh_from_db()
    assert "watchers_notified" in link.detail
    with patch("mesh_monitoring.tasks.notify_watchers_node_replaced", side_effect=RuntimeError("boom")):
        Link.objects.filter(pk=link.pk).update(detail={})
        result = process_node_watch_presence()
    assert result["replaced"] == 1
    link.refresh_from_db()
    assert "watchers_notified" in link.detail


@pytest.fixture
def predicted_pair(replaced_pair):
    """The replaced_pair, but the link rests only on a predicted number and the new row's key is unheard."""
    user, old, new, link = replaced_pair
    link.evidence = Link.Evidence.PREDICTED_NUMBER
    link.confidence = Link.Confidence.MEDIUM
    link.save(update_fields=["evidence", "confidence"])
    return user, old, new, link


@pytest.mark.django_db
def test_predicted_only_link_does_not_pause_or_dm(predicted_pair, verified):
    _, old, _, link = predicted_pair
    with patch("push_notifications.discord_audit.send_dm"):
        with patch("mesh_monitoring.tasks._dispatch_monitoring_round"):
            result = process_node_watch_presence()
    assert result["replaced"] == 0 and result["watched"] == 1
    assert not DiscordNotificationAudit.objects.filter(kind=DiscordNotificationKind.NODE_REPLACED).exists()
    link.refresh_from_db()
    assert "watchers_notified" not in link.detail


@pytest.mark.django_db
def test_predicted_only_link_does_not_skip_learned_thresholds(predicted_pair):
    assert update_learned_offline_thresholds() == {"updated": 1, "failed": 0}


@pytest.mark.django_db
def test_predicted_link_pauses_and_dms_once_key_is_heard(predicted_pair, verified):
    _, old, new, link = predicted_pair
    new.meshtastic_public_key_hex = "ab" * 32
    new.save(update_fields=["meshtastic_public_key_hex"])
    with patch("push_notifications.discord_audit.send_dm") as send_dm:
        result = process_node_watch_presence()
    assert result == {"watched": 0, "replaced": 1}
    assert send_dm.call_count == 1
