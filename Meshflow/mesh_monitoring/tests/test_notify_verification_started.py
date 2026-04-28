"""Discord notify when mesh monitoring starts verification (#165)."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test.utils import override_settings
from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
from mesh_monitoring.constants import notify_verification_start_enabled, verification_notify_cooldown_seconds
from mesh_monitoring.models import NodePresence
from mesh_monitoring.tasks import process_node_watch_presence
from mesh_monitoring.tests.conftest import create_watch_with_offline_threshold
from nodes.tasks import update_managed_node_statuses
from traceroute.tasks import dispatch_pending_traceroutes


def test_notify_verification_start_enabled_default_true_when_unset(monkeypatch):
    monkeypatch.delenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", raising=False)
    assert notify_verification_start_enabled() is True


def test_notify_verification_start_enabled_explicit_off(monkeypatch):
    monkeypatch.setenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", "false")
    assert notify_verification_start_enabled() is False
    monkeypatch.setenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", "0")
    assert notify_verification_start_enabled() is False


def test_notify_verification_start_enabled_truthy(monkeypatch):
    monkeypatch.setenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", "true")
    assert notify_verification_start_enabled() is True
    monkeypatch.setenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", "1")
    assert notify_verification_start_enabled() is True


def test_verification_notify_cooldown_seconds_default(monkeypatch):
    monkeypatch.delenv("MESH_MONITORING_VERIFICATION_NOTIFY_COOLDOWN_SECONDS", raising=False)
    assert verification_notify_cooldown_seconds() == 3600


@pytest.mark.django_db
def test_verification_start_notify_happy_path(
    monkeypatch,
    create_user,
    create_observed_node,
    create_managed_node,
    create_packet_observation,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    monkeypatch.setenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", "1")

    user = create_user()
    obs = create_observed_node(node_id=0xAABBCCDD, claimed_by=user)
    obs.last_heard = timezone.now() - timedelta(seconds=120)
    obs.save(update_fields=["last_heard"])
    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)

    mn = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=48.0,
        default_location_longitude=2.0,
    )
    create_packet_observation(observer=mn)
    update_managed_node_statuses()

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    with override_settings(FRONTEND_URL="https://mesh.example"):
        with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
            with patch("push_notifications.discord_audit.send_dm") as send_dm:
                with patch("traceroute.lifecycle.notify_traceroute_status_changed"):
                    with patch("traceroute.dispatch.notify_traceroute_status_changed"):
                        with patch("traceroute.dispatch.async_to_sync", side_effect=immediate_async_to_sync):
                            with patch("traceroute.dispatch.get_channel_layer", return_value=channel_layer):
                                process_node_watch_presence()
                                dispatch_pending_traceroutes()

    send_dm.assert_called_once()
    body = send_dm.call_args[0][1]
    assert obs.node_id_str in body
    assert "60" in body
    assert "https://mesh.example/nodes/" in body
    presence = NodePresence.objects.get(observed_node=obs)
    assert presence.last_verification_notify_at is not None


@pytest.mark.django_db
def test_verification_start_notify_skipped_when_flag_off(
    monkeypatch,
    create_user,
    create_observed_node,
    create_managed_node,
    create_packet_observation,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    monkeypatch.setenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", "false")

    user = create_user()
    obs = create_observed_node(node_id=0xBBCCDDEE, claimed_by=user)
    obs.last_heard = timezone.now() - timedelta(seconds=120)
    obs.save(update_fields=["last_heard"])
    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)
    mn = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=48.0,
        default_location_longitude=2.0,
    )
    create_packet_observation(observer=mn)
    update_managed_node_statuses()

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
        with patch("push_notifications.discord_audit.send_dm") as send_dm:
            with patch("traceroute.lifecycle.notify_traceroute_status_changed"):
                with patch("traceroute.dispatch.notify_traceroute_status_changed"):
                    with patch("traceroute.dispatch.async_to_sync", side_effect=immediate_async_to_sync):
                        with patch("traceroute.dispatch.get_channel_layer", return_value=channel_layer):
                            process_node_watch_presence()
                            dispatch_pending_traceroutes()

    send_dm.assert_not_called()


@pytest.mark.django_db
def test_verification_start_notify_respects_cooldown(
    monkeypatch,
    create_user,
    create_observed_node,
    create_managed_node,
    create_packet_observation,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    monkeypatch.setenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", "1")
    monkeypatch.setenv("MESH_MONITORING_VERIFICATION_NOTIFY_COOLDOWN_SECONDS", "3600")

    user = create_user()
    obs = create_observed_node(node_id=0xCCDDEEFF, claimed_by=user)
    obs.last_heard = timezone.now() - timedelta(seconds=120)
    obs.save(update_fields=["last_heard"])
    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)
    NodePresence.objects.filter(observed_node=obs).update(
        last_verification_notify_at=timezone.now() - timedelta(minutes=1),
    )
    mn = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=48.0,
        default_location_longitude=2.0,
    )
    create_packet_observation(observer=mn)
    update_managed_node_statuses()

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
        with patch("push_notifications.discord_audit.send_dm") as send_dm:
            with patch("traceroute.lifecycle.notify_traceroute_status_changed"):
                with patch("traceroute.dispatch.notify_traceroute_status_changed"):
                    with patch("traceroute.dispatch.async_to_sync", side_effect=immediate_async_to_sync):
                        with patch("traceroute.dispatch.get_channel_layer", return_value=channel_layer):
                            process_node_watch_presence()
                            dispatch_pending_traceroutes()

    send_dm.assert_not_called()


@pytest.mark.django_db
def test_not_silent_clears_last_verification_notify_at(
    create_user,
    create_observed_node,
):
    user = create_user()
    obs = create_observed_node(node_id=0xDDEEFF00, claimed_by=user)
    obs.last_heard = timezone.now()
    obs.save(update_fields=["last_heard"])
    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)
    NodePresence.objects.filter(observed_node=obs).update(
        last_verification_notify_at=timezone.now() - timedelta(hours=1),
        verification_started_at=timezone.now() - timedelta(minutes=5),
    )

    process_node_watch_presence()

    presence = NodePresence.objects.get(observed_node=obs)
    assert presence.last_verification_notify_at is None
    assert presence.verification_started_at is None
