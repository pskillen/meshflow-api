"""Dispatch queue: per-source pacing, status transitions (meshflow-api#226)."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import override_settings
from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from traceroute import dispatch
from traceroute.models import AutoTraceRoute
from traceroute.tasks import dispatch_pending_traceroutes


def _patched_channel_send():
    channel_layer = MagicMock()

    def immediate(async_func):
        return async_func

    return (
        channel_layer,
        patch("traceroute.dispatch.async_to_sync", side_effect=immediate),
        patch("traceroute.dispatch.get_channel_layer", return_value=channel_layer),
        patch("traceroute.dispatch.notify_traceroute_status_changed"),
    )


@pytest.mark.django_db
@override_settings()
def test_try_dispatch_sends_due_not_future(
    monkeypatch,
    create_user,
    create_managed_node,
    create_observed_node,
):
    monkeypatch.setattr(dispatch, "DISPATCH_PER_SOURCE_INTERVAL_SEC", 0, raising=False)
    a = create_managed_node(allow_auto_traceroute=True)
    b = create_observed_node()
    u = create_user()
    future = timezone.now() + timedelta(hours=1)
    t_future = AutoTraceRoute.objects.create(
        source_node=a,
        target_node=b,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
        triggered_by=u,
        status=AutoTraceRoute.STATUS_PENDING,
        earliest_send_at=future,
    )
    t_now = AutoTraceRoute.objects.create(
        source_node=a,
        target_node=b,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
        triggered_by=u,
        status=AutoTraceRoute.STATUS_PENDING,
        earliest_send_at=timezone.now() - timedelta(seconds=1),
    )
    ch, p_async, p_ch, p_notify = _patched_channel_send()
    with p_notify, p_async, p_ch:
        r1 = dispatch.try_dispatch_one()
    assert r1["outcome"] == "dispatched"
    assert r1["id"] == t_now.id
    t_now.refresh_from_db()
    t_future.refresh_from_db()
    assert t_now.status == AutoTraceRoute.STATUS_SENT
    assert t_future.status == AutoTraceRoute.STATUS_PENDING
    ch.group_send.assert_called_once()


@pytest.mark.django_db
@override_settings()
def test_cooldown_second_row_same_source_waits(
    monkeypatch,
    create_managed_node,
    create_observed_node,
):
    a = create_managed_node(allow_auto_traceroute=True)
    b = create_observed_node(node_id=0xAABB0001)
    c = create_observed_node(node_id=0xAABB0002)
    at = timezone.now()
    t1 = AutoTraceRoute.objects.create(
        source_node=a,
        target_node=b,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
        triggered_by=None,
        trigger_source="test",
        status=AutoTraceRoute.STATUS_PENDING,
        earliest_send_at=at,
    )
    t2 = AutoTraceRoute.objects.create(
        source_node=a,
        target_node=c,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
        triggered_by=None,
        trigger_source="test",
        status=AutoTraceRoute.STATUS_PENDING,
        earliest_send_at=at,
    )
    monkeypatch.setattr(dispatch, "DISPATCH_PER_SOURCE_INTERVAL_SEC", 300, raising=False)
    ch, p_async, p_ch, p_notify = _patched_channel_send()
    with p_notify, p_async, p_ch:
        r1 = dispatch.try_dispatch_one()
    assert r1["outcome"] == "dispatched"
    t1.refresh_from_db()
    assert t1.status == AutoTraceRoute.STATUS_SENT
    with p_notify, p_async, p_ch:
        r2 = dispatch.try_dispatch_one()
    assert r2.get("outcome") == "all_cooldown"
    t2.refresh_from_db()
    assert t2.status == AutoTraceRoute.STATUS_PENDING

    t1.dispatched_at = timezone.now() - timedelta(seconds=500)
    t1.save(update_fields=["dispatched_at"])
    with p_notify, p_async, p_ch:
        r3 = dispatch.try_dispatch_one()
    assert r3["outcome"] == "dispatched"
    t2.refresh_from_db()
    assert t2.status == AutoTraceRoute.STATUS_SENT
    assert ch.group_send.call_count == 2


@pytest.mark.django_db
@override_settings()
def test_channel_error_increments_attempts_keeps_pending(
    create_user,
    create_managed_node,
    create_observed_node,
):
    """Dispatch errors are visible on the row; status stays pending."""
    a = create_managed_node(allow_auto_traceroute=True)
    b = create_observed_node()
    u = create_user()
    t = AutoTraceRoute.objects.create(
        source_node=a,
        target_node=b,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
        triggered_by=u,
        status=AutoTraceRoute.STATUS_PENDING,
        earliest_send_at=timezone.now(),
    )
    with patch("traceroute.dispatch.async_to_sync", side_effect=OSError("channel test failure")):
        with patch("traceroute.dispatch.get_channel_layer", return_value=MagicMock()):
            r = dispatch.try_dispatch_one()
    assert r.get("outcome") == "error"
    t.refresh_from_db()
    assert t.status == AutoTraceRoute.STATUS_PENDING
    assert t.dispatch_attempts == 1
    assert t.dispatch_error


@pytest.mark.django_db
@override_settings()
def test_concurrent_select_for_update_does_not_double_send(
    monkeypatch,
    create_user,
    create_managed_node,
    create_observed_node,
):
    """At most one worker sends a given due row: second pass sees nothing or cooldown."""
    monkeypatch.setattr(dispatch, "DISPATCH_PER_SOURCE_INTERVAL_SEC", 0, raising=False)
    a = create_managed_node(allow_auto_traceroute=True)
    b = create_observed_node()
    u = create_user()
    t = AutoTraceRoute.objects.create(
        source_node=a,
        target_node=b,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
        triggered_by=u,
        status=AutoTraceRoute.STATUS_PENDING,
        earliest_send_at=timezone.now(),
    )
    ch, p_async, p_ch, p_notify = _patched_channel_send()
    with p_notify, p_async, p_ch:
        d1 = dispatch_pending_traceroutes()["dispatched"]
        d2 = dispatch_pending_traceroutes()["dispatched"]
    t.refresh_from_db()
    assert d1 == 1
    assert d2 == 0
    assert t.status == AutoTraceRoute.STATUS_SENT
    ch.group_send.assert_called_once()
