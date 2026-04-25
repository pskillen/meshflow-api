"""Tests for traceroute Celery tasks."""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401 - load fixtures
import users.tests.conftest  # noqa: F401 - load fixtures
from traceroute.models import AutoTraceRoute
from traceroute.tasks import mark_stale_traceroutes_failed


@pytest.mark.django_db
def test_mark_stale_traceroutes_failed(create_auto_traceroute):
    """Stale pending/sent traceroutes are marked failed after 180s."""
    tr = create_auto_traceroute(status=AutoTraceRoute.STATUS_SENT)
    tr.triggered_at = timezone.now() - timedelta(seconds=200)
    tr.save(update_fields=["triggered_at"])

    with patch("traceroute.tasks.notify_traceroute_status_changed"):
        result = mark_stale_traceroutes_failed()

    assert result["updated"] == 1
    tr.refresh_from_db()
    assert tr.status == AutoTraceRoute.STATUS_FAILED
    assert tr.completed_at is not None
    assert "180" in (tr.error_message or "")


@pytest.mark.django_db
def test_mark_stale_traceroutes_failed_ignores_recent(create_auto_traceroute):
    """Recent pending/sent traceroutes are not marked failed."""
    tr = create_auto_traceroute(status=AutoTraceRoute.STATUS_SENT)
    tr.triggered_at = timezone.now() - timedelta(seconds=60)
    tr.save(update_fields=["triggered_at"])

    with patch("traceroute.tasks.notify_traceroute_status_changed"):
        result = mark_stale_traceroutes_failed()

    assert result["updated"] == 0
    tr.refresh_from_db()
    assert tr.status == AutoTraceRoute.STATUS_SENT


@pytest.mark.django_db
def test_mark_stale_ignores_pending_not_yet_due(
    create_managed_node,
    create_observed_node,
    create_user,
):
    """Pending rows with ``earliest_send_at`` in the future are not timed out on ``triggered_at`` alone."""
    u = create_user()
    a = create_managed_node()
    b = create_observed_node()
    future = timezone.now() + timedelta(hours=2)
    tr = AutoTraceRoute.objects.create(
        source_node=a,
        target_node=b,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
        triggered_by=u,
        status=AutoTraceRoute.STATUS_PENDING,
        triggered_at=timezone.now() - timedelta(hours=10),
        earliest_send_at=future,
    )

    with patch("traceroute.tasks.notify_traceroute_status_changed"):
        result = mark_stale_traceroutes_failed()
    assert result["updated"] == 0
    tr.refresh_from_db()
    assert tr.status == AutoTraceRoute.STATUS_PENDING


@pytest.mark.django_db
def test_mark_stale_pending_uses_earliest_send_at(create_user, create_managed_node, create_observed_node):
    """Failed pending: ``earliest_send_at`` (due time) is older than timeout, not just ``triggered_at``."""
    u = create_user()
    a = create_managed_node()
    b = create_observed_node()
    past = timezone.now() - timedelta(seconds=200)
    tr = AutoTraceRoute.objects.create(
        source_node=a,
        target_node=b,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
        triggered_by=u,
        status=AutoTraceRoute.STATUS_PENDING,
        triggered_at=timezone.now(),
        earliest_send_at=past,
    )
    with patch("traceroute.tasks.notify_traceroute_status_changed"):
        result = mark_stale_traceroutes_failed()
    assert result["updated"] == 1
    tr.refresh_from_db()
    assert tr.status == AutoTraceRoute.STATUS_FAILED
