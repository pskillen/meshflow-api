"""Celery task process_node_watch_presence."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
from mesh_monitoring.models import NodePresence, NodeWatch
from mesh_monitoring.services import monitoring_traceroute_succeeded_since, on_monitoring_traceroute_completed
from mesh_monitoring.tasks import process_node_watch_presence
from mesh_monitoring.tests.conftest import create_watch_with_offline_threshold
from nodes.models import NodeLatestStatus
from nodes.tasks import update_managed_node_statuses
from traceroute.models import AutoTraceRoute
from traceroute.tasks import dispatch_pending_traceroutes


@pytest.mark.django_db
def test_process_node_watch_presence_starts_verification_and_creates_monitor_tr(
    monkeypatch,
    create_user,
    create_observed_node,
    create_managed_node,
    create_packet_observation,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")

    user = create_user()
    obs = create_observed_node(node_id=112233445, claimed_by=user)
    obs.last_heard = timezone.now() - timedelta(seconds=120)
    obs.save(update_fields=["last_heard"])
    NodeLatestStatus.objects.create(node=obs, latitude=48.0, longitude=2.0)

    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)

    mn = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=48.1,
        default_location_longitude=2.1,
    )
    create_packet_observation(observer=mn)
    update_managed_node_statuses()

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    with patch("traceroute.lifecycle.notify_traceroute_status_changed"):
        with patch("traceroute.dispatch.notify_traceroute_status_changed"):
            with patch("traceroute.dispatch.async_to_sync", side_effect=immediate_async_to_sync):
                with patch("traceroute.dispatch.get_channel_layer", return_value=channel_layer):
                    result = process_node_watch_presence()
                    dispatch_pending_traceroutes()

    assert result["watched"] >= 1
    assert NodePresence.objects.filter(observed_node=obs, verification_started_at__isnull=False).exists()
    assert AutoTraceRoute.objects.filter(
        target_node=obs,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_NODE_WATCH,
        trigger_source="mesh_monitoring",
    ).exists()
    channel_layer.group_send.assert_called()

    presence = NodePresence.objects.get(observed_node=obs)
    assert presence.verification_started_at is not None
    assert presence.suspected_offline_at is not None
    assert presence.suspected_offline_at == presence.verification_started_at
    assert presence.tr_sent_count >= 1
    assert presence.last_tr_sent is not None
    assert presence.last_zero_sources_at is None
    assert presence.is_offline is False
    assert presence.observed_online_at is None


@pytest.mark.django_db
def test_monitoring_traceroute_succeeded_since_true_when_route_empty(
    create_user, create_observed_node, create_managed_node
):
    """Completed monitor TR with direct path (empty route lists) counts as success."""
    user = create_user()
    obs = create_observed_node(node_id=0x11223344, claimed_by=user)
    source = create_managed_node()
    since = timezone.now() - timedelta(minutes=10)
    AutoTraceRoute.objects.create(
        source_node=source,
        target_node=obs,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_NODE_WATCH,
        triggered_by=None,
        trigger_source="mesh_monitoring",
        status=AutoTraceRoute.STATUS_COMPLETED,
        route=[],
        route_back=[],
        triggered_at=timezone.now() - timedelta(minutes=1),
    )
    assert monitoring_traceroute_succeeded_since(obs, since) is True


@pytest.mark.django_db
def test_on_monitoring_traceroute_completed_clears_verification_when_routes_empty(
    create_user, create_observed_node, create_managed_node
):
    """Direct-path monitor completion clears verification_started_at."""
    user = create_user()
    obs = create_observed_node(node_id=0x22334455, claimed_by=user)
    vs = timezone.now() - timedelta(minutes=2)
    NodePresence.objects.create(observed_node=obs, verification_started_at=vs)
    source = create_managed_node()
    auto_tr = AutoTraceRoute.objects.create(
        source_node=source,
        target_node=obs,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_NODE_WATCH,
        triggered_by=None,
        trigger_source="mesh_monitoring",
        status=AutoTraceRoute.STATUS_COMPLETED,
        route=[],
        route_back=[],
        triggered_at=timezone.now() - timedelta(seconds=30),
    )
    on_monitoring_traceroute_completed(auto_tr)
    presence = NodePresence.objects.get(observed_node=obs)
    assert presence.verification_started_at is None
    assert presence.suspected_offline_at is None
    assert presence.last_tr_sent is None
    assert presence.last_zero_sources_at is None
    assert presence.tr_sent_count == 0


@pytest.mark.django_db
def test_dispatch_zero_sources_sets_last_zero_sources_at(
    monkeypatch,
    create_user,
    create_observed_node,
    create_managed_node,
    create_packet_observation,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")

    user = create_user()
    obs = create_observed_node(node_id=0x33445566, claimed_by=user)
    obs.last_heard = timezone.now() - timedelta(seconds=120)
    obs.save(update_fields=["last_heard"])
    NodeLatestStatus.objects.create(node=obs, latitude=48.0, longitude=2.0)
    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)

    mn = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=48.1,
        default_location_longitude=2.1,
    )
    create_packet_observation(observer=mn)
    update_managed_node_statuses()

    with patch("mesh_monitoring.tasks.select_monitoring_sources", return_value=[]):
        process_node_watch_presence()

    presence = NodePresence.objects.get(observed_node=obs)
    assert presence.verification_started_at is not None
    assert presence.last_zero_sources_at is not None
    assert not AutoTraceRoute.objects.filter(target_node=obs, trigger_source="mesh_monitoring").exists()


@pytest.mark.django_db
def test_process_node_watch_presence_clears_observability_when_node_not_silent(
    create_user,
    create_observed_node,
):
    user = create_user()
    obs = create_observed_node(node_id=0x44556677, claimed_by=user)
    obs.last_heard = timezone.now() - timedelta(seconds=120)
    obs.save(update_fields=["last_heard"])
    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)
    NodePresence.objects.filter(observed_node=obs).update(
        verification_started_at=timezone.now() - timedelta(minutes=5),
        suspected_offline_at=timezone.now() - timedelta(minutes=5),
        tr_sent_count=2,
        last_tr_sent=timezone.now() - timedelta(minutes=1),
        last_zero_sources_at=timezone.now() - timedelta(minutes=10),
    )

    obs.last_heard = timezone.now()
    obs.save(update_fields=["last_heard"])
    process_node_watch_presence()

    presence = NodePresence.objects.get(observed_node=obs)
    assert presence.verification_started_at is None
    assert presence.suspected_offline_at is None
    assert presence.last_tr_sent is None
    assert presence.last_zero_sources_at is None
    assert presence.tr_sent_count == 0
    assert presence.is_offline is False


@pytest.mark.django_db
def test_process_node_watch_presence_sets_observed_online_at_when_created_heard(
    create_user,
    create_observed_node,
):
    """First presence row while last_heard is fresh records observed_online_at."""
    user = create_user()
    obs = create_observed_node(node_id=0x66778899, claimed_by=user)
    obs.last_heard = timezone.now()
    obs.save(update_fields=["last_heard"])
    NodeWatch.objects.create(user=user, observed_node=obs, enabled=True)

    process_node_watch_presence()

    presence = NodePresence.objects.get(observed_node=obs)
    assert presence.observed_online_at is not None
    assert presence.is_offline is False
    assert presence.verification_started_at is None


@pytest.mark.django_db
def test_process_node_watch_presence_recovery_from_offline_sets_observed_online_at(
    create_user,
    create_observed_node,
):
    user = create_user()
    obs = create_observed_node(node_id=0x778899AA, claimed_by=user)
    obs.last_heard = timezone.now()
    obs.save(update_fields=["last_heard"])
    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)
    NodePresence.objects.filter(observed_node=obs).update(
        offline_confirmed_at=timezone.now() - timedelta(hours=1),
        is_offline=True,
    )

    process_node_watch_presence()

    presence = NodePresence.objects.get(observed_node=obs)
    assert presence.is_offline is False
    assert presence.offline_confirmed_at is None
    assert presence.observed_online_at is not None


@pytest.mark.django_db
def test_process_node_watch_presence_offline_confirm_sets_is_offline(
    monkeypatch,
    create_user,
    create_observed_node,
    create_managed_node,
    create_packet_observation,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")

    user = create_user()
    obs = create_observed_node(node_id=0x88990011, claimed_by=user)
    now = timezone.now()
    obs.last_heard = now - timedelta(minutes=10)
    obs.save(update_fields=["last_heard"])
    NodeLatestStatus.objects.create(node=obs, latitude=48.0, longitude=2.0)
    create_watch_with_offline_threshold(user=user, observed_node=obs, offline_after=60)
    vs = now - timedelta(minutes=2)
    NodePresence.objects.filter(observed_node=obs).update(verification_started_at=vs)

    mn = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=48.1,
        default_location_longitude=2.1,
    )
    create_packet_observation(observer=mn)
    update_managed_node_statuses()

    monkeypatch.setattr(
        "mesh_monitoring.tasks.verification_window_seconds",
        lambda: 1,
    )
    with patch("mesh_monitoring.tasks.notify_watchers_node_offline", return_value=0):
        process_node_watch_presence()

    presence = NodePresence.objects.get(observed_node=obs)
    assert presence.is_offline is True
    assert presence.offline_confirmed_at is not None
    assert presence.verification_started_at is None


@pytest.mark.django_db
def test_send_monitoring_traceroute_command_updates_presence_tr_fields(
    create_user,
    create_observed_node,
    create_managed_node,
):
    user = create_user()
    obs = create_observed_node(node_id=0x55667788, claimed_by=user)
    NodePresence.objects.get_or_create(observed_node=obs)
    source = create_managed_node(allow_auto_traceroute=True)
    at = timezone.now()
    auto_tr = AutoTraceRoute.objects.create(
        source_node=source,
        target_node=obs,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_NODE_WATCH,
        triggered_by=None,
        trigger_source="mesh_monitoring",
        status=AutoTraceRoute.STATUS_PENDING,
        earliest_send_at=at,
    )
    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    with patch("traceroute.dispatch.notify_traceroute_status_changed"):
        with patch("traceroute.dispatch.async_to_sync", side_effect=immediate_async_to_sync):
            with patch("traceroute.dispatch.get_channel_layer", return_value=channel_layer):
                assert dispatch_pending_traceroutes()["dispatched"] == 1

    presence = NodePresence.objects.get(observed_node=obs)
    assert presence.tr_sent_count == 1
    assert presence.last_tr_sent is not None
    auto_tr.refresh_from_db()
    assert auto_tr.status == AutoTraceRoute.STATUS_SENT
