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
