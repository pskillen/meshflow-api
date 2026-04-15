"""Celery task process_node_watch_presence."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
from mesh_monitoring.models import NodePresence, NodeWatch
from mesh_monitoring.tasks import process_node_watch_presence, send_monitoring_traceroute_command
from nodes.models import NodeLatestStatus
from traceroute.models import AutoTraceRoute


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

    NodeWatch.objects.create(user=user, observed_node=obs, offline_after=60, enabled=True)

    mn = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=48.1,
        default_location_longitude=2.1,
    )
    create_packet_observation(observer=mn)

    channel_layer = MagicMock()

    def immediate_async_to_sync(async_func):
        return async_func

    def sync_apply_async(*, args=(), **kwargs):
        send_monitoring_traceroute_command(*args)

    with patch("mesh_monitoring.tasks.async_to_sync", side_effect=immediate_async_to_sync):
        with patch("mesh_monitoring.tasks.get_channel_layer", return_value=channel_layer):
            with patch.object(
                send_monitoring_traceroute_command,
                "apply_async",
                side_effect=sync_apply_async,
            ):
                result = process_node_watch_presence()

    assert result["watched"] >= 1
    assert NodePresence.objects.filter(observed_node=obs, verification_started_at__isnull=False).exists()
    assert AutoTraceRoute.objects.filter(
        target_node=obs,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITOR,
        trigger_source="mesh_monitoring",
    ).exists()
    channel_layer.group_send.assert_called()
