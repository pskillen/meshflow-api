"""An exclusion on an earlier number of a node applies to its new number, for traceroute hops and exploration."""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from dx_monitoring.exploration import plan_event_exploration
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
from nodes.models import NodeLatestStatus, ObservedNodeIdentityLink
from traceroute.models import AutoTraceRoute


def _coords(node, lat, lon):
    NodeLatestStatus.objects.update_or_create(node=node, defaults={"latitude": lat, "longitude": lon})


def _link(old, new, state="auto"):
    return ObservedNodeIdentityLink.objects.create(
        old_node=old, new_node=new, evidence="public_key", confidence="strong", state=state
    )


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_TRACEROUTE_HOP_DISTANCE_KM=150.0,
)
@pytest.mark.parametrize(
    "link_state, excluded, expect_event",
    [
        ("auto", True, False),  # excluded node upgraded: no traceroute_distant_hop for its new number
        ("confirmed", True, False),
        ("auto", False, True),  # control: not excluded, the same hop raises the event
        ("suggested", True, True),  # only live links carry an exclusion
        ("rejected", True, True),
    ],
)
def test_traceroute_hop_exclusion_is_read_through_identity_links(
    link_state,
    excluded,
    expect_event,
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    source = create_managed_node(
        meshtastic_node_id=0xEE000020,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    create_user()
    target = create_observed_node(meshtastic_node_id=0xEE0000BB)
    old = create_observed_node(meshtastic_node_id=0xEE0000C1)
    hop = create_observed_node(meshtastic_node_id=0xEE0000C2)
    _coords(hop, 51.5, -0.12)  # far from the Edinburgh source
    if excluded:
        DxNodeMetadata.objects.create(observed_node=old, exclude_from_detection=True)
    _link(old, hop, state=link_state)

    route = [hop.meshtastic_node_id]
    auto_tr = AutoTraceRoute.objects.create(
        source_node=source,
        target_node=target,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
        status=AutoTraceRoute.STATUS_COMPLETED,
        earliest_send_at=timezone.now(),
        triggered_at=timezone.now(),
        completed_at=timezone.now(),
        route=route,
        route_back=[],
    )
    packet = create_traceroute_packet(
        observer=source,
        from_int=target.meshtastic_node_id,
        route=route,
        route_back=[],
        snr_towards=[],
        snr_back=[],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source)

    maybe_detect_dx_from_completed_traceroute(auto_tr, packet, observation)

    assert DxEvent.objects.filter(reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP).exists() is expect_event
    assert not DxNodeMetadata.objects.filter(observed_node=hop).exists()


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_EXPLORATION_ENABLED=True,
    DX_MONITORING_EXPLORATION_MAX_SOURCES_PER_EVENT=1,
)
def test_exploration_skips_the_new_number_of_an_excluded_node(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
    create_user,
):
    create_user()
    source = create_managed_node(
        meshtastic_node_id=0xAB000511,
        allow_auto_traceroute=True,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    mark_managed_node_feeding(source, sending=True)
    old = create_observed_node(meshtastic_node_id=0xAB0005A1)
    dest = create_observed_node(meshtastic_node_id=0xAB0005A2)
    _coords(dest, 51.5, -0.12)
    DxNodeMetadata.objects.create(observed_node=old, exclude_from_detection=True)
    _link(old, dest)

    now = timezone.now()
    event = DxEvent.objects.create(
        constellation=source.constellation,
        destination=dest,
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=2),
        last_observer=source,
    )
    plan_event_exploration(event)

    skip = DxEventTraceroute.objects.get(event=event)
    assert skip.outcome == DxEventTracerouteOutcome.SKIPPED
    assert skip.skip_reason == DxEventTracerouteSkipReason.DESTINATION_EXCLUDED
    assert not DxNodeMetadata.objects.filter(observed_node=dest).exists()
