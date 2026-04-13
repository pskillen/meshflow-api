"""Tests for schedule_traceroutes Celery task."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
from traceroute.models import AutoTraceRoute
from traceroute.tasks import schedule_traceroutes


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
    target = create_observed_node(node_id=111222333)

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    with patch("traceroute.tasks.async_to_sync", side_effect=immediate_async_to_sync):
        with patch("traceroute.tasks.get_channel_layer", return_value=channel_layer):
            with patch("traceroute.tasks.pick_traceroute_target", return_value=target):
                assert schedule_traceroutes() == {"created": 1}

    assert AutoTraceRoute.objects.filter(
        source_node=mn,
        target_node=target,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_AUTO,
        trigger_source="scheduler",
    ).exists()
    channel_layer.group_send.assert_called_once()
    call_kw = channel_layer.group_send.call_args[0]
    assert call_kw[0] == f"node_{mn.node_id}"
    assert call_kw[1]["type"] == "node_command"
    assert call_kw[1]["command"] == {"type": "traceroute", "target": target.node_id}
