"""Unit tests for traceroute.lifecycle queueing and completion helpers."""

from unittest.mock import patch

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from traceroute.lifecycle import (
    apply_auto_traceroute_completion,
    apply_auto_traceroute_failure,
    create_external_inferred_auto_traceroute,
    create_pending_auto_traceroute,
    schedule_completed_traceroute_neo4j_export,
)
from traceroute.models import AutoTraceRoute


@pytest.mark.django_db
def test_create_pending_auto_traceroute_notifies_by_default(
    create_managed_node,
    create_observed_node,
    create_user,
):
    source = create_managed_node()
    target = create_observed_node()
    u = create_user()
    at = timezone.now()
    with patch("traceroute.lifecycle.notify_traceroute_status_changed") as mock_notify:
        tr = create_pending_auto_traceroute(
            source_node=source,
            target_node=target,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
            triggered_by=u,
            trigger_source="test",
            target_strategy=None,
            earliest_send_at=at,
        )
    mock_notify.assert_called_once_with(tr.id, AutoTraceRoute.STATUS_PENDING)
    assert tr.status == AutoTraceRoute.STATUS_PENDING
    assert tr.trigger_source == "test"


@pytest.mark.django_db
def test_create_pending_auto_traceroute_notify_optional(
    create_managed_node,
    create_observed_node,
):
    source = create_managed_node()
    target = create_observed_node()
    with patch("traceroute.lifecycle.notify_traceroute_status_changed") as mock_notify:
        create_pending_auto_traceroute(
            source_node=source,
            target_node=target,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
            triggered_by=None,
            trigger_source="scheduler",
            target_strategy=AutoTraceRoute.TARGET_STRATEGY_LEGACY,
            notify_pending=False,
        )
    mock_notify.assert_not_called()


@pytest.mark.django_db
def test_apply_auto_traceroute_completion_persists_fields(
    create_managed_node,
    create_observed_node,
    create_user,
):
    from packets.models import TraceroutePacket

    source = create_managed_node()
    target = create_observed_node()
    u = create_user()
    tr = AutoTraceRoute.objects.create(
        source_node=source,
        target_node=target,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
        triggered_by=u,
        status=AutoTraceRoute.STATUS_SENT,
    )
    packet = TraceroutePacket.objects.create(
        packet_id=111,
        from_int=target.node_id,
        from_str=target.node_id_str,
        to_int=source.node_id,
        to_str=source.node_id_str,
        port_num="TRACEROUTE_APP",
        route=[1, 2],
        route_back=[2, 1],
        snr_towards=[-1.0, -2.0],
        snr_back=[-1.5, -2.5],
    )
    route = [{"node_id": 1, "snr": -1.0}]
    route_back = [{"node_id": 2, "snr": -2.0}]
    apply_auto_traceroute_completion(tr, route=route, route_back=route_back, raw_packet=packet)
    tr.refresh_from_db()
    assert tr.status == AutoTraceRoute.STATUS_COMPLETED
    assert tr.route == route
    assert tr.route_back == route_back
    assert tr.raw_packet_id == packet.id
    assert tr.completed_at is not None
    assert tr.error_message is None


def test_schedule_completed_traceroute_neo4j_export_delegates():
    with patch("traceroute.tasks.push_traceroute_to_neo4j") as mock_push:
        schedule_completed_traceroute_neo4j_export(42)
    mock_push.delay.assert_called_once_with(42)


@pytest.mark.django_db
def test_create_external_inferred_auto_traceroute(
    create_managed_node,
    create_observed_node,
):
    source = create_managed_node()
    target = create_observed_node()
    tr = create_external_inferred_auto_traceroute(source_node=source, target_node=target)
    assert tr.trigger_type == AutoTraceRoute.TRIGGER_TYPE_EXTERNAL
    assert tr.status == AutoTraceRoute.STATUS_PENDING
    assert tr.trigger_source is None
    assert tr.triggered_by_id is None


@pytest.mark.django_db
def test_apply_auto_traceroute_failure_persists_fields(
    create_managed_node,
    create_observed_node,
    create_user,
):
    source = create_managed_node()
    target = create_observed_node()
    u = create_user()
    tr = AutoTraceRoute.objects.create(
        source_node=source,
        target_node=target,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
        triggered_by=u,
        status=AutoTraceRoute.STATUS_SENT,
    )
    apply_auto_traceroute_failure(tr, error_message="timed out")
    tr.refresh_from_db()
    assert tr.status == AutoTraceRoute.STATUS_FAILED
    assert tr.error_message == "timed out"
    assert tr.completed_at is not None
