"""Discord notify when mesh monitoring starts verification (#165)."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test.utils import override_settings
from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
from mesh_monitoring.constants import notify_verification_start_enabled, verification_notify_cooldown_seconds
from mesh_monitoring.models import NodePresence, NodeWatch
from mesh_monitoring.tasks import process_node_watch_presence, send_monitoring_traceroute_command


def test_notify_verification_start_enabled_default_false(monkeypatch):
    monkeypatch.delenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", raising=False)
    assert notify_verification_start_enabled() is False


def test_notify_verification_start_enabled_truthy(monkeypatch):
    monkeypatch.setenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", "true")
    assert notify_verification_start_enabled() is True
    monkeypatch.setenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", "1")
    assert notify_verification_start_enabled() is True


def test_verification_notify_cooldown_seconds_default(monkeypatch):
    monkeypatch.delenv("MESH_MONITORING_VERIFICATION_NOTIFY_COOLDOWN_SECONDS", raising=False)
    assert verification_notify_cooldown_seconds() == 21600


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
    NodeWatch.objects.create(user=user, observed_node=obs, offline_after=60, enabled=True)

    mn = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=48.0,
        default_location_longitude=2.0,
    )
    create_packet_observation(observer=mn)

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    def sync_apply_async(*, args=(), **kwargs):
        send_monitoring_traceroute_command(*args)

    with override_settings(FRONTEND_URL="https://mesh.example"):
        with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
            with patch("mesh_monitoring.services.send_dm") as send_dm:
                with patch("mesh_monitoring.tasks.async_to_sync", side_effect=immediate_async_to_sync):
                    with patch("mesh_monitoring.tasks.get_channel_layer", return_value=channel_layer):
                        with patch.object(
                            send_monitoring_traceroute_command,
                            "apply_async",
                            side_effect=sync_apply_async,
                        ):
                            process_node_watch_presence()

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
    monkeypatch.delenv("MESH_MONITORING_NOTIFY_VERIFICATION_START", raising=False)

    user = create_user()
    obs = create_observed_node(node_id=0xBBCCDDEE, claimed_by=user)
    obs.last_heard = timezone.now() - timedelta(seconds=120)
    obs.save(update_fields=["last_heard"])
    NodeWatch.objects.create(user=user, observed_node=obs, offline_after=60, enabled=True)
    mn = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=48.0,
        default_location_longitude=2.0,
    )
    create_packet_observation(observer=mn)

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    def sync_apply_async(*, args=(), **kwargs):
        send_monitoring_traceroute_command(*args)

    with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
        with patch("mesh_monitoring.services.send_dm") as send_dm:
            with patch("mesh_monitoring.tasks.async_to_sync", side_effect=immediate_async_to_sync):
                with patch("mesh_monitoring.tasks.get_channel_layer", return_value=channel_layer):
                    with patch.object(
                        send_monitoring_traceroute_command,
                        "apply_async",
                        side_effect=sync_apply_async,
                    ):
                        process_node_watch_presence()

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
    NodeWatch.objects.create(user=user, observed_node=obs, offline_after=60, enabled=True)
    NodePresence.objects.create(
        observed_node=obs,
        last_verification_notify_at=timezone.now() - timedelta(minutes=1),
    )
    mn = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=48.0,
        default_location_longitude=2.0,
    )
    create_packet_observation(observer=mn)

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    def sync_apply_async(*, args=(), **kwargs):
        send_monitoring_traceroute_command(*args)

    with patch("mesh_monitoring.services.user_has_verified_discord_dm_target", return_value=True):
        with patch("mesh_monitoring.services.send_dm") as send_dm:
            with patch("mesh_monitoring.tasks.async_to_sync", side_effect=immediate_async_to_sync):
                with patch("mesh_monitoring.tasks.get_channel_layer", return_value=channel_layer):
                    with patch.object(
                        send_monitoring_traceroute_command,
                        "apply_async",
                        side_effect=sync_apply_async,
                    ):
                        process_node_watch_presence()

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
    NodeWatch.objects.create(user=user, observed_node=obs, offline_after=60, enabled=True)
    NodePresence.objects.create(
        observed_node=obs,
        last_verification_notify_at=timezone.now() - timedelta(hours=1),
        verification_started_at=timezone.now() - timedelta(minutes=5),
    )

    process_node_watch_presence()

    presence = NodePresence.objects.get(observed_node=obs)
    assert presence.last_verification_notify_at is None
    assert presence.verification_started_at is None
