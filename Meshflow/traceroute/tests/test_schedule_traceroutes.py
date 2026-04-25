"""Tests for schedule_traceroutes Celery task."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
from nodes.tasks import update_managed_node_statuses
from traceroute.models import AutoTraceRoute
from traceroute.tasks import dispatch_pending_traceroutes, schedule_traceroutes


@pytest.mark.django_db
def test_schedule_traceroutes_no_eligible_without_observation(monkeypatch, create_managed_node):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    create_managed_node(allow_auto_traceroute=True)

    assert schedule_traceroutes() == {"created": 0}
    assert AutoTraceRoute.objects.count() == 0


@pytest.mark.django_db
def test_schedule_traceroutes_excludes_stale_observation(monkeypatch, create_managed_node, create_packet_observation):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    mn = create_managed_node(allow_auto_traceroute=True)
    obs = create_packet_observation(observer=mn)
    obs.upload_time = timezone.now() - timedelta(seconds=700)
    obs.save(update_fields=["upload_time"])
    update_managed_node_statuses()

    assert schedule_traceroutes() == {"created": 0}
    assert AutoTraceRoute.objects.count() == 0


@pytest.mark.django_db
def test_schedule_traceroutes_creates_when_recent_observation(
    monkeypatch,
    create_managed_node,
    create_packet_observation,
    create_observed_node,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    mn = create_managed_node(allow_auto_traceroute=True)
    create_packet_observation(observer=mn)
    update_managed_node_statuses()
    target = create_observed_node(node_id=111222333)

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    with patch("traceroute.tasks.notify_traceroute_status_changed") as mock_ws:
        with patch("traceroute.dispatch.notify_traceroute_status_changed"):
            with patch("traceroute.dispatch.async_to_sync", side_effect=immediate_async_to_sync):
                with patch("traceroute.dispatch.get_channel_layer", return_value=channel_layer):
                    with patch(
                        "traceroute.tasks.eligible_traceroute_sources_ordered",
                        return_value=[mn],
                    ):
                        with patch(
                            "traceroute.tasks.ordered_strategies_for_feeder",
                            return_value=[AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS],
                        ):
                            with patch("traceroute.tasks.pick_traceroute_target", return_value=target):
                                assert schedule_traceroutes() == {"created": 1}
                                assert dispatch_pending_traceroutes()["dispatched"] == 1

    tr = AutoTraceRoute.objects.get(
        source_node=mn,
        target_node=target,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
        trigger_source="scheduler",
        target_strategy=AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS,
    )
    mock_ws.assert_called_once_with(tr.id, AutoTraceRoute.STATUS_PENDING)
    assert tr.status == AutoTraceRoute.STATUS_SENT
    assert tr.dispatched_at is not None
    channel_layer.group_send.assert_called_once()
    call_kw = channel_layer.group_send.call_args[0]
    assert call_kw[0] == f"node_{mn.node_id}"
    assert call_kw[1]["type"] == "node_command"
    assert call_kw[1]["command"] == {"type": "traceroute", "target": target.node_id}
