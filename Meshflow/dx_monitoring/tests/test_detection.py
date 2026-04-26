"""Tests for DX candidate detection during packet processing."""

from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from common.mesh_node_helpers import meshtastic_id_to_hex
from dx_monitoring.models import DxEvent, DxEventObservation, DxNodeMetadata, DxReasonCode
from nodes.models import NodeLatestStatus, ObservedNode
from packets.services.node_info import NodeInfoPacketService
from packets.services.position import PositionPacketService
from packets.services.traceroute import TraceroutePacketService


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=5000.0,
    DX_MONITORING_RETURNED_DX_QUIET_DAYS=30,
    DX_MONITORING_EVENT_ACTIVE_MINUTES=60,
)
def test_node_info_then_position_emits_new_distant_node(
    create_managed_node,
    create_packet_observation,
    create_user,
    create_node_info_packet,
    create_position_packet,
):
    observer = create_managed_node(
        node_id=0xE2000001,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    remote_id = 0xBEEF0202
    remote_hex = meshtastic_id_to_hex(remote_id)

    ninfo = create_node_info_packet(
        packet_id=900001,
        from_int=remote_id,
        from_str=remote_hex,
        node_id=remote_hex,
    )
    obs1 = create_packet_observation(packet=ninfo, observer=observer)
    NodeInfoPacketService().process_packet(ninfo, observer, obs1, user)

    assert not DxEvent.objects.filter(reason_code=DxReasonCode.NEW_DISTANT_NODE).exists()

    pos = create_position_packet(
        packet_id=900002,
        from_int=remote_id,
        from_str=remote_hex,
        latitude=51.5,
        longitude=-0.12,
    )
    pos.first_reported_time = timezone.now()
    pos.save(update_fields=["first_reported_time"])
    obs2 = create_packet_observation(packet=pos, observer=observer)
    PositionPacketService().process_packet(pos, observer, obs2, user)

    ev = DxEvent.objects.get(reason_code=DxReasonCode.NEW_DISTANT_NODE)
    assert ev.constellation_id == observer.constellation_id
    assert ev.destination.node_id == remote_id
    assert ev.observation_count == 1
    assert DxEventObservation.objects.filter(event=ev).count() == 1


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=5000.0,
)
def test_position_packet_deduplicates_new_distant_within_active_window(
    create_managed_node,
    create_packet_observation,
    create_user,
    create_position_packet,
):
    observer = create_managed_node(
        node_id=0xE2000002,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    remote_id = 0xBEEF0203
    remote_hex = meshtastic_id_to_hex(remote_id)

    def run_packet(packet_id):
        pos = create_position_packet(
            packet_id=packet_id,
            from_int=remote_id,
            from_str=remote_hex,
            latitude=51.5,
            longitude=-0.12,
        )
        pos.first_reported_time = timezone.now()
        pos.save(update_fields=["first_reported_time"])
        obs = create_packet_observation(packet=pos, observer=observer)
        PositionPacketService().process_packet(pos, observer, obs, user)

    run_packet(910001)
    run_packet(910002)

    ev = DxEvent.objects.get(reason_code=DxReasonCode.NEW_DISTANT_NODE)
    assert ev.observation_count == 2
    assert DxEventObservation.objects.filter(event=ev).count() == 2


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=5000.0,
    DX_MONITORING_RETURNED_DX_QUIET_DAYS=30,
)
def test_returned_dx_node_after_quiet_period(
    create_managed_node,
    create_packet_observation,
    create_user,
    create_position_packet,
):
    observer = create_managed_node(
        node_id=0xE2000003,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    remote_id = 0xBEEF0204
    remote_hex = meshtastic_id_to_hex(remote_id)

    t0 = timezone.now()
    pos1 = create_position_packet(
        packet_id=920001,
        from_int=remote_id,
        from_str=remote_hex,
        latitude=51.5,
        longitude=-0.12,
    )
    pos1.first_reported_time = t0
    pos1.save(update_fields=["first_reported_time"])
    obs1 = create_packet_observation(packet=pos1, observer=observer)
    PositionPacketService().process_packet(pos1, observer, obs1, user)

    assert DxEvent.objects.filter(reason_code=DxReasonCode.NEW_DISTANT_NODE).count() == 1

    dest = ObservedNode.objects.get(node_id=remote_id)
    dest.last_heard = t0 - timedelta(days=40)
    dest.save(update_fields=["last_heard"])

    pos2 = create_position_packet(
        packet_id=920002,
        from_int=remote_id,
        from_str=remote_hex,
        latitude=51.51,
        longitude=-0.11,
    )
    pos2.first_reported_time = t0
    pos2.save(update_fields=["first_reported_time"])
    obs2 = create_packet_observation(packet=pos2, observer=observer)
    PositionPacketService().process_packet(pos2, observer, obs2, user)

    assert DxEvent.objects.filter(reason_code=DxReasonCode.RETURNED_DX_NODE).count() == 1


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=80.0,
)
def test_distant_observation_direct_threshold(
    create_managed_node,
    create_packet_observation,
    create_user,
    create_position_packet,
):
    observer = create_managed_node(
        node_id=0xE2000004,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    remote_id = 0xBEEF0205
    remote_hex = meshtastic_id_to_hex(remote_id)

    pos = create_position_packet(
        packet_id=930001,
        from_int=remote_id,
        from_str=remote_hex,
        latitude=51.5,
        longitude=-0.12,
    )
    pos.first_reported_time = timezone.now()
    pos.save(update_fields=["first_reported_time"])
    obs = create_packet_observation(packet=pos, observer=observer)
    PositionPacketService().process_packet(pos, observer, obs, user)

    assert DxEvent.objects.filter(reason_code=DxReasonCode.DISTANT_OBSERVATION).exists()


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=5000.0,
)
def test_exclude_from_detection_skips_events(
    create_observed_node,
    create_managed_node,
    create_packet_observation,
    create_user,
    create_position_packet,
):
    observer = create_managed_node(
        node_id=0xE2000005,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    remote_id = 0xBEEF0206
    remote_hex = meshtastic_id_to_hex(remote_id)

    pos = create_position_packet(
        packet_id=940001,
        from_int=remote_id,
        from_str=remote_hex,
        latitude=51.5,
        longitude=-0.12,
    )
    pos.first_reported_time = timezone.now()
    pos.save(update_fields=["first_reported_time"])
    dest = create_observed_node(node_id=remote_id)
    DxNodeMetadata.objects.create(observed_node=dest, exclude_from_detection=True)

    obs = create_packet_observation(packet=pos, observer=observer)
    PositionPacketService().process_packet(pos, observer, obs, user)

    assert not DxEvent.objects.exists()


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=5000.0,
)
def test_self_observer_packet_skipped(
    create_managed_node,
    create_packet_observation,
    create_user,
    create_position_packet,
):
    nid = 0xE2000006
    observer = create_managed_node(
        node_id=nid,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    remote_hex = meshtastic_id_to_hex(nid)

    pos = create_position_packet(
        packet_id=950001,
        from_int=nid,
        from_str=remote_hex,
        latitude=51.5,
        longitude=-0.12,
    )
    pos.first_reported_time = timezone.now()
    pos.save(update_fields=["first_reported_time"])
    obs = create_packet_observation(packet=pos, observer=observer)
    PositionPacketService().process_packet(pos, observer, obs, user)

    assert not DxEvent.objects.exists()


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=5000.0,
)
def test_multihop_packet_does_not_emit_packet_ingest_dx(
    create_managed_node,
    create_packet_observation,
    create_user,
    create_position_packet,
):
    """Non-direct observations (relay hops remaining) must not open packet-ingest DX."""
    observer = create_managed_node(
        node_id=0xE2000011,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    remote_id = 0xBEEF0211
    remote_hex = meshtastic_id_to_hex(remote_id)

    pos = create_position_packet(
        packet_id=960001,
        from_int=remote_id,
        from_str=remote_hex,
        latitude=51.5,
        longitude=-0.12,
    )
    pos.first_reported_time = timezone.now()
    pos.save(update_fields=["first_reported_time"])
    obs = create_packet_observation(packet=pos, observer=observer, hop_start=3, hop_limit=2)
    PositionPacketService().process_packet(pos, observer, obs, user)

    assert not DxEvent.objects.exists()


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=5000.0,
)
def test_missing_hop_metadata_does_not_emit_packet_ingest_dx(
    create_managed_node,
    create_packet_observation,
    create_user,
    create_position_packet,
):
    observer = create_managed_node(
        node_id=0xE2000012,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    remote_id = 0xBEEF0212
    remote_hex = meshtastic_id_to_hex(remote_id)

    pos = create_position_packet(
        packet_id=960002,
        from_int=remote_id,
        from_str=remote_hex,
        latitude=51.5,
        longitude=-0.12,
    )
    pos.first_reported_time = timezone.now()
    pos.save(update_fields=["first_reported_time"])
    obs = create_packet_observation(packet=pos, observer=observer, hop_start=None, hop_limit=3)
    PositionPacketService().process_packet(pos, observer, obs, user)

    assert not DxEvent.objects.exists()


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=5000.0,
)
def test_observer_node_suppressed_skips_dx_events(
    create_managed_node,
    create_observed_node,
    create_packet_observation,
    create_user,
    create_position_packet,
):
    """When the observer's mesh id is excluded via DxNodeMetadata, skip packet-ingest DX."""
    observer = create_managed_node(
        node_id=0xE2000013,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    obs_row = create_observed_node(node_id=observer.node_id)
    DxNodeMetadata.objects.create(observed_node=obs_row, exclude_from_detection=True)

    user = create_user()
    remote_id = 0xBEEF0213
    remote_hex = meshtastic_id_to_hex(remote_id)

    pos = create_position_packet(
        packet_id=960003,
        from_int=remote_id,
        from_str=remote_hex,
        latitude=51.5,
        longitude=-0.12,
    )
    pos.first_reported_time = timezone.now()
    pos.save(update_fields=["first_reported_time"])
    obs = create_packet_observation(packet=pos, observer=observer)
    PositionPacketService().process_packet(pos, observer, obs, user)

    assert not DxEvent.objects.exists()


def _set_node_coords(observed_node: ObservedNode, lat: float, lon: float) -> None:
    NodeLatestStatus.objects.update_or_create(
        node=observed_node,
        defaults={"latitude": lat, "longitude": lon},
    )


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_TRACEROUTE_HOP_DISTANCE_KM=150.0,
)
def test_traceroute_empty_route_far_hop_emits_traceroute_distant_hop(
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    source = create_managed_node(
        node_id=0xE2000020,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    target = create_observed_node(node_id=0xBEEF0220)
    _set_node_coords(target, 51.5, -0.12)

    packet = create_traceroute_packet(
        observer=source,
        from_int=target.node_id,
        route=[],
        route_back=[],
        snr_towards=[],
        snr_back=[],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source)

    with patch("traceroute.tasks.push_traceroute_to_neo4j"):
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            TraceroutePacketService().process_packet(packet, source, observation, user)

    ev = DxEvent.objects.get(reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP)
    assert ev.destination_id == target.pk
    meta = ev.observations.first().metadata
    assert meta["path_direction"] == "forward"
    assert meta["from_node_id"] == int(source.node_id)
    assert meta["to_node_id"] == int(target.node_id)


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_TRACEROUTE_HOP_DISTANCE_KM=500.0,
)
def test_traceroute_near_hop_does_not_emit(
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    source = create_managed_node(
        node_id=0xE2000021,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    target = create_observed_node(node_id=0xBEEF0221)
    _set_node_coords(target, 55.96, -3.18)

    packet = create_traceroute_packet(
        observer=source,
        from_int=target.node_id,
        route=[],
        route_back=[],
        snr_towards=[],
        snr_back=[],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source)

    with patch("traceroute.tasks.push_traceroute_to_neo4j"):
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            TraceroutePacketService().process_packet(packet, source, observation, user)

    assert not DxEvent.objects.filter(reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP).exists()


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_TRACEROUTE_HOP_DISTANCE_KM=150.0,
)
def test_traceroute_suppressed_endpoint_skips(
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    source = create_managed_node(
        node_id=0xE2000022,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    target = create_observed_node(node_id=0xBEEF0222)
    _set_node_coords(target, 51.5, -0.12)
    DxNodeMetadata.objects.create(observed_node=target, exclude_from_detection=True)

    packet = create_traceroute_packet(
        observer=source,
        from_int=target.node_id,
        route=[],
        route_back=[],
        snr_towards=[],
        snr_back=[],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source)

    with patch("traceroute.tasks.push_traceroute_to_neo4j"):
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            TraceroutePacketService().process_packet(packet, source, observation, user)

    assert not DxEvent.objects.exists()


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_TRACEROUTE_HOP_DISTANCE_KM=150.0,
)
def test_traceroute_forward_and_return_paths_evaluated(
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    """Return path includes a long hop to an intermediate observed node."""
    source = create_managed_node(
        node_id=0xE2000023,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    target = create_observed_node(node_id=0xBEEF0223)
    relay = create_observed_node(node_id=0xCAFE0223)
    _set_node_coords(target, 51.5, -0.12)
    _set_node_coords(relay, 53.48, -2.24)

    packet = create_traceroute_packet(
        observer=source,
        from_int=target.node_id,
        route=[],
        route_back=[relay.node_id],
        snr_towards=[],
        snr_back=[-4.0],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source)

    with patch("traceroute.tasks.push_traceroute_to_neo4j"):
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            TraceroutePacketService().process_packet(packet, source, observation, user)

    directions = set(
        DxEventObservation.objects.filter(
            event__reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP,
        ).values_list("metadata__path_direction", flat=True)
    )
    assert "forward" in directions
    assert "return" in directions


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_TRACEROUTE_HOP_DISTANCE_KM=150.0,
)
def test_traceroute_skips_hop_when_relay_has_no_position(
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    """Pairs involving a relay without coordinates are skipped; a later hop can still match."""
    source = create_managed_node(
        node_id=0xE2000024,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    user = create_user()
    target = create_observed_node(node_id=0xBEEF0224)
    relay_no_pos = create_observed_node(node_id=0xCAFE0224)
    relay_pos = create_observed_node(node_id=0xCAFE0225)
    _set_node_coords(target, 51.5, -0.12)
    _set_node_coords(relay_pos, 53.4, -2.98)

    packet = create_traceroute_packet(
        observer=source,
        from_int=target.node_id,
        route=[relay_no_pos.node_id, relay_pos.node_id],
        route_back=[relay_pos.node_id, relay_no_pos.node_id],
        snr_towards=[-5.0, -3.0],
        snr_back=[-4.0, -2.0],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source)

    with patch("traceroute.tasks.push_traceroute_to_neo4j"):
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            TraceroutePacketService().process_packet(packet, source, observation, user)

    evs = DxEvent.objects.filter(reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP)
    assert evs.filter(destination=target).count() == 1
    assert not evs.filter(destination=relay_no_pos).exists()
