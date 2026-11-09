"""DX detection ignores positions too coarse to support a distance rule."""

from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from common.mesh_node_helpers import meshtastic_id_to_hex
from dx_monitoring.models import DxEvent, DxEventObservation, DxReasonCode
from nodes.models import NodeLatestStatus, ObservedNode
from packets.services.position import PositionPacketService
from packets.services.traceroute import TraceroutePacketService


def _run_position(
    *, observer, create_packet_observation, create_user, create_position_packet, packet_id, remote_id, bits
):
    pos = create_position_packet(
        packet_id=packet_id,
        from_int=remote_id,
        from_str=meshtastic_id_to_hex(remote_id),
        latitude=51.5,
        longitude=-0.12,
        meshtastic_precision_bits=bits,
    )
    pos.first_reported_time = timezone.now()
    pos.save(update_fields=["first_reported_time"])
    obs = create_packet_observation(packet=pos, observer=observer)
    PositionPacketService().process_packet(pos, observer, obs, create_user())


@pytest.mark.django_db
@pytest.mark.parametrize("bits", [13, 15, 32, None])
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=80.0,
)
def test_precise_enough_position_still_raises_events(
    bits, create_managed_node, create_packet_observation, create_user, create_position_packet
):
    observer = create_managed_node(
        meshtastic_node_id=0xE2000040,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    _run_position(
        observer=observer,
        create_packet_observation=create_packet_observation,
        create_user=create_user,
        create_position_packet=create_position_packet,
        packet_id=940001,
        remote_id=0xBEEF0240,
        bits=bits,
    )
    assert DxEvent.objects.filter(reason_code=DxReasonCode.NEW_DISTANT_NODE).exists()
    assert DxEvent.objects.filter(reason_code=DxReasonCode.DISTANT_OBSERVATION).exists()
    meta = DxEventObservation.objects.filter(event__reason_code=DxReasonCode.NEW_DISTANT_NODE).first().metadata
    if bits in (13, 15):
        assert meta["uncertainty_km"] > 0
    else:
        assert "uncertainty_km" not in meta


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=80.0,
)
def test_nine_bit_position_raises_no_distance_events(
    create_managed_node, create_packet_observation, create_user, create_position_packet
):
    observer = create_managed_node(
        meshtastic_node_id=0xE2000041,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    _run_position(
        observer=observer,
        create_packet_observation=create_packet_observation,
        create_user=create_user,
        create_position_packet=create_position_packet,
        packet_id=940002,
        remote_id=0xBEEF0241,
        bits=9,
    )
    assert not DxEvent.objects.filter(
        reason_code__in=[DxReasonCode.NEW_DISTANT_NODE, DxReasonCode.DISTANT_OBSERVATION]
    ).exists()


def _set_node_coords_bits(observed_node: ObservedNode, lat: float, lon: float, bits: int | None) -> None:
    NodeLatestStatus.objects.update_or_create(
        node=observed_node,
        defaults={"latitude": lat, "longitude": lon, "meshtastic_precision_bits": bits},
    )


@pytest.mark.django_db
@pytest.mark.parametrize("relay_bits,expect_event", [(9, False), (15, True)])
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_TRACEROUTE_HOP_DISTANCE_KM=150.0,
)
def test_traceroute_hop_with_coarse_end_is_skipped(
    relay_bits,
    expect_event,
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    source = create_managed_node(
        meshtastic_node_id=0xE2000042,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    target = create_observed_node(meshtastic_node_id=0xBEEF0242)
    relay = create_observed_node(meshtastic_node_id=0xCAFE0242)
    # Only the return-path hop to the relay is far; the target sits next to the source.
    _set_node_coords_bits(target, 55.96, -3.20, 32)
    _set_node_coords_bits(relay, 51.5, -0.12, relay_bits)

    packet = create_traceroute_packet(
        observer=source,
        from_int=target.meshtastic_node_id,
        route=[],
        route_back=[relay.meshtastic_node_id],
        snr_towards=[],
        snr_back=[-4.0],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source)
    with patch("traceroute.tasks.push_traceroute_to_neo4j"):
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            TraceroutePacketService().process_packet(packet, source, observation, create_user())

    assert DxEvent.objects.filter(reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP).exists() is expect_event
