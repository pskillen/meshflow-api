"""Tests for DX traceroute exploration (#221)."""

from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from dx_monitoring.exploration import (
    TRIGGER_SOURCE,
    active_events_due_for_exploration,
    baseline_row_for_target,
    on_auto_traceroute_exploration_finished,
    ordered_exploration_sources,
    plan_event_exploration,
    scan_active_dx_events_for_traceroutes,
)
from dx_monitoring.models import (
    DxEvent,
    DxEventState,
    DxEventTraceroute,
    DxEventTracerouteOutcome,
    DxEventTracerouteSkipReason,
    DxNodeMetadata,
    DxReasonCode,
)
from dx_monitoring.services import maybe_detect_dx_from_completed_traceroute
from nodes.models import NodeLatestStatus
from packets.services.traceroute import TraceroutePacketService
from traceroute.models import AutoTraceRoute


def _coords(on, lat, lon):
    NodeLatestStatus.objects.update_or_create(node=on, defaults={"latitude": lat, "longitude": lon})


def _dx_event(*, constellation, destination, last_observer, **kwargs):
    now = timezone.now()
    return DxEvent.objects.create(
        constellation=constellation,
        destination=destination,
        reason_code=kwargs.pop("reason_code", DxReasonCode.NEW_DISTANT_NODE),
        state=kwargs.pop("state", DxEventState.ACTIVE),
        first_observed_at=kwargs.pop("first_observed_at", now),
        last_observed_at=kwargs.pop("last_observed_at", now),
        active_until=kwargs.pop("active_until", now + timedelta(hours=2)),
        last_observer=last_observer,
        **kwargs,
    )


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_EXPLORATION_ENABLED=True,
    DX_MONITORING_EXPLORATION_MAX_SOURCES_PER_EVENT=2,
)
def test_ordered_exploration_sources_prefers_last_observer(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
):
    lo = create_managed_node(
        node_id=0xAA000001,
        allow_auto_traceroute=True,
        default_location_latitude=55.0,
        default_location_longitude=-3.0,
    )
    owner = lo.owner
    c = lo.constellation
    other = create_managed_node(
        owner=owner,
        constellation=c,
        node_id=0xAA000002,
        allow_auto_traceroute=True,
        default_location_latitude=55.1,
        default_location_longitude=-3.1,
    )
    for mn in (lo, other):
        mark_managed_node_feeding(mn, sending=True)

    dest = create_observed_node(node_id=0xBB000099)
    _coords(dest, 51.5, -0.12)
    ev = _dx_event(constellation=c, destination=dest, last_observer=lo)

    ordered = ordered_exploration_sources(ev)
    assert ordered[0].pk == lo.pk


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_EXPLORATION_ENABLED=True,
    DX_MONITORING_EXPLORATION_MAX_SOURCES_PER_EVENT=1,
    DX_MONITORING_EXPLORATION_BASELINE_RECENCY_MINUTES=120,
)
def test_plan_links_pending_baseline_instead_of_duplicate_dx_watch(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
    create_user,
):
    create_user()
    source = create_managed_node(
        node_id=0xCC000001,
        allow_auto_traceroute=True,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    mark_managed_node_feeding(source, sending=True)
    dest = create_observed_node(node_id=0xCC000099)
    _coords(dest, 51.5, -0.12)

    baseline = AutoTraceRoute.objects.create(
        source_node=source,
        target_node=dest,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE,
        trigger_source="new_node_observed",
        triggered_by=None,
        status=AutoTraceRoute.STATUS_PENDING,
        earliest_send_at=timezone.now(),
    )

    ev = _dx_event(
        constellation=source.constellation,
        destination=dest,
        last_observer=source,
    )
    plan_event_exploration(ev)

    assert not AutoTraceRoute.objects.filter(
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_DX_WATCH,
        trigger_source=TRIGGER_SOURCE,
    ).exists()
    et = DxEventTraceroute.objects.get(event=ev)
    assert et.outcome == DxEventTracerouteOutcome.PENDING
    assert et.auto_traceroute_id == baseline.id
    assert et.metadata.get("link_kind") == "new_node_baseline"


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_EXPLORATION_ENABLED=True,
    DX_MONITORING_EXPLORATION_MAX_SOURCES_PER_EVENT=1,
    DX_MONITORING_EXPLORATION_BASELINE_RECENCY_MINUTES=120,
)
def test_plan_records_completed_baseline_as_exploration_evidence(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
    create_user,
):
    create_user()
    source = create_managed_node(
        node_id=0xCC000002,
        allow_auto_traceroute=True,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    mark_managed_node_feeding(source, sending=True)
    dest = create_observed_node(node_id=0xCC000098)
    _coords(dest, 51.5, -0.12)

    AutoTraceRoute.objects.create(
        source_node=source,
        target_node=dest,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE,
        trigger_source="new_node_observed",
        triggered_by=None,
        status=AutoTraceRoute.STATUS_COMPLETED,
        earliest_send_at=timezone.now(),
        completed_at=timezone.now(),
        route=[{"node_id": int(source.node_id), "snr": -1.0}],
    )

    ev = _dx_event(
        constellation=source.constellation,
        destination=dest,
        last_observer=source,
    )
    plan_event_exploration(ev)

    et = DxEventTraceroute.objects.get(event=ev)
    assert et.outcome == DxEventTracerouteOutcome.COMPLETED
    assert et.metadata.get("link_kind") == "new_node_baseline"


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_EXPLORATION_ENABLED=True,
    DX_MONITORING_EXPLORATION_MAX_SOURCES_PER_EVENT=1,
)
def test_plan_queues_dx_watch_with_expected_fields(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
    create_user,
):
    create_user()
    source = create_managed_node(
        node_id=0xDD000001,
        allow_auto_traceroute=True,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    mark_managed_node_feeding(source, sending=True)
    dest = create_observed_node(node_id=0xDD000099)
    _coords(dest, 51.5, -0.12)

    assert baseline_row_for_target(dest) is None

    ev = _dx_event(
        constellation=source.constellation,
        destination=dest,
        last_observer=source,
    )
    with patch("dx_monitoring.exploration.notify_traceroute_status_changed"):
        plan_event_exploration(ev)

    tr = AutoTraceRoute.objects.get(
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_DX_WATCH,
        trigger_source=TRIGGER_SOURCE,
    )
    assert tr.source_node_id == source.pk
    assert tr.target_node_id == dest.pk
    assert tr.status == AutoTraceRoute.STATUS_PENDING

    et = DxEventTraceroute.objects.get(event=ev)
    assert et.auto_traceroute_id == tr.id
    assert et.outcome == DxEventTracerouteOutcome.PENDING


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_EXPLORATION_ENABLED=True,
    DX_MONITORING_EXPLORATION_MAX_SOURCES_PER_EVENT=1,
)
def test_completion_marks_dx_event_traceroute_completed(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    user = create_user()
    source = create_managed_node(
        node_id=0xEE000001,
        allow_auto_traceroute=True,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    mark_managed_node_feeding(source, sending=True)
    dest = create_observed_node(node_id=0xEE000099)
    _coords(dest, 51.5, -0.12)

    auto_tr = AutoTraceRoute.objects.create(
        source_node=source,
        target_node=dest,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_DX_WATCH,
        trigger_source=TRIGGER_SOURCE,
        triggered_by=None,
        status=AutoTraceRoute.STATUS_SENT,
        earliest_send_at=timezone.now(),
        triggered_at=timezone.now(),
        dispatched_at=timezone.now(),
    )
    ev = _dx_event(constellation=source.constellation, destination=dest, last_observer=source)
    DxEventTraceroute.objects.create(
        event=ev,
        auto_traceroute=auto_tr,
        source_node=source,
        outcome=DxEventTracerouteOutcome.PENDING,
        metadata={"link_kind": "dx_watch"},
    )

    packet = create_traceroute_packet(
        observer=source,
        from_int=dest.node_id,
        route=[],
        route_back=[],
        snr_towards=[],
        snr_back=[],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source)

    with patch("traceroute.tasks.push_traceroute_to_neo4j"):
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            with patch("mesh_monitoring.services.on_monitoring_traceroute_completed"):
                TraceroutePacketService().process_packet(packet, source, observation, user)

    et = DxEventTraceroute.objects.get(event=ev)
    assert et.outcome == DxEventTracerouteOutcome.COMPLETED
    assert et.metadata.get("route_hops") == 0


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_TRACEROUTE_HOP_DISTANCE_KM=150.0,
)
def test_maybe_detect_skips_distant_hop_for_exploration_destination(
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    """Linked exploration TR should not also create traceroute_distant_hop evidence for the same hop."""
    source = create_managed_node(
        node_id=0xEE000010,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    create_user()
    target = create_observed_node(node_id=0xEE0000AA)
    _coords(target, 51.5, -0.12)

    auto_tr = AutoTraceRoute.objects.create(
        source_node=source,
        target_node=target,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_DX_WATCH,
        trigger_source=TRIGGER_SOURCE,
        triggered_by=None,
        status=AutoTraceRoute.STATUS_COMPLETED,
        earliest_send_at=timezone.now(),
        triggered_at=timezone.now(),
        completed_at=timezone.now(),
        route=[],
        route_back=[],
    )
    ev = _dx_event(constellation=source.constellation, destination=target, last_observer=source)
    DxEventTraceroute.objects.create(
        event=ev,
        auto_traceroute=auto_tr,
        source_node=source,
        outcome=DxEventTracerouteOutcome.COMPLETED,
        metadata={},
    )

    packet = create_traceroute_packet(
        observer=source,
        from_int=target.node_id,
        route=[],
        route_back=[],
        snr_towards=[],
        snr_back=[],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source)

    maybe_detect_dx_from_completed_traceroute(auto_tr, packet, observation)

    assert not DxEvent.objects.filter(reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP).exists()


@pytest.mark.django_db
@override_settings(DX_MONITORING_EXPLORATION_ENABLED=False)
def test_scan_skips_when_exploration_disabled():
    assert scan_active_dx_events_for_traceroutes()["skipped_disabled"] is True


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_EXPLORATION_ENABLED=True,
    DX_MONITORING_EXPLORATION_EVENT_COOLDOWN_MINUTES=60,
    DX_MONITORING_EXPLORATION_MAX_SOURCES_PER_EVENT=1,
)
def test_active_events_not_due_immediately_after_plan_attempt(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
    create_user,
):
    create_user()
    source = create_managed_node(
        node_id=0xFF000001,
        allow_auto_traceroute=True,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    mark_managed_node_feeding(source, sending=True)
    dest = create_observed_node(node_id=0xFF000099)
    _coords(dest, 51.5, -0.12)
    ev = _dx_event(constellation=source.constellation, destination=dest, last_observer=source)

    assert active_events_due_for_exploration().filter(pk=ev.pk).exists()

    with patch("dx_monitoring.exploration.notify_traceroute_status_changed"):
        plan_event_exploration(ev)

    assert not active_events_due_for_exploration().filter(pk=ev.pk).exists()


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_EXPLORATION_ENABLED=True,
    DX_MONITORING_EXPLORATION_MAX_SOURCES_PER_EVENT=1,
)
def test_plan_skips_when_destination_metadata_excludes_detection(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
    create_user,
):
    create_user()
    source = create_managed_node(
        node_id=0xAB000501,
        allow_auto_traceroute=True,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    mark_managed_node_feeding(source, sending=True)
    dest = create_observed_node(node_id=0xAB000599)
    _coords(dest, 51.5, -0.12)
    DxNodeMetadata.objects.create(observed_node=dest, exclude_from_detection=True)

    ev = _dx_event(constellation=source.constellation, destination=dest, last_observer=source)
    plan_event_exploration(ev)

    skip = DxEventTraceroute.objects.get(event=ev)
    assert skip.outcome == DxEventTracerouteOutcome.SKIPPED
    assert skip.skip_reason == DxEventTracerouteSkipReason.DESTINATION_EXCLUDED


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_EXPLORATION_ENABLED=True,
    DX_MONITORING_EXPLORATION_MAX_SOURCES_PER_EVENT=1,
)
def test_on_auto_marks_linked_rows_failed_for_baseline(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
    create_user,
):
    create_user()
    source = create_managed_node(
        node_id=0xAB000601,
        allow_auto_traceroute=True,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    mark_managed_node_feeding(source, sending=True)
    dest = create_observed_node(node_id=0xAB000699)
    _coords(dest, 51.5, -0.12)

    baseline = AutoTraceRoute.objects.create(
        source_node=source,
        target_node=dest,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE,
        trigger_source="new_node_observed",
        triggered_by=None,
        status=AutoTraceRoute.STATUS_FAILED,
        earliest_send_at=timezone.now(),
        completed_at=timezone.now(),
        error_message="x",
    )
    ev = _dx_event(constellation=source.constellation, destination=dest, last_observer=source)
    et = DxEventTraceroute.objects.create(
        event=ev,
        auto_traceroute=baseline,
        source_node=source,
        outcome=DxEventTracerouteOutcome.PENDING,
        metadata={"link_kind": "new_node_baseline"},
    )

    on_auto_traceroute_exploration_finished(baseline)

    et.refresh_from_db()
    assert et.outcome == DxEventTracerouteOutcome.FAILED
