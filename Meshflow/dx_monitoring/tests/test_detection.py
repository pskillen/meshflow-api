"""Tests for DX candidate detection during packet processing."""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from common.mesh_node_helpers import meshtastic_id_to_hex
from dx_monitoring.models import DxEvent, DxEventObservation, DxNodeMetadata, DxReasonCode
from nodes.models import ObservedNode
from packets.services.node_info import NodeInfoPacketService
from packets.services.position import PositionPacketService


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
