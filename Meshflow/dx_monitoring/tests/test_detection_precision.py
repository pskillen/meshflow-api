"""DX detection ignores positions too coarse to support a distance rule."""

from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from common.geo import position_uncertainty_km
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


# Observer: Edinburgh (55.95, -3.19). One degree of latitude is 111.2 km.
# lat 55.05 is about 100 km south, lat 54.51 about 160 km south, London about 535 km.


def _run_position_at(
    *, observer, create_packet_observation, create_user, create_position_packet, packet_id, remote_id, bits, lat, lon
):
    pos = create_position_packet(
        packet_id=packet_id,
        from_int=remote_id,
        from_str=meshtastic_id_to_hex(remote_id),
        latitude=lat,
        longitude=lon,
        meshtastic_precision_bits=bits,
    )
    pos.first_reported_time = timezone.now()
    pos.save(update_fields=["first_reported_time"])
    obs = create_packet_observation(packet=pos, observer=observer)
    PositionPacketService().process_packet(pos, observer, obs, create_user())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "bits,lat,lon,expect_cluster,expect_direct",
    [
        # 9 bits (46.7 km) at 100 km: 53 km is inside the 80 km direct threshold, so it could be a false DX.
        (9, 55.05, -3.19, False, False),
        # 15 bits (0.73 km) at the same place: certainly beyond 80 km.
        (15, 55.05, -3.19, False, True),
        # 10 bits (23.3 km) at 160 km: 136.7 km is inside the 150 km cluster threshold but beyond 80 km direct.
        (10, 54.51, -3.19, False, True),
        # The same place at 15 bits is beyond both.
        (15, 54.51, -3.19, True, True),
        # 10 bits at 110 km: 86.7 km is still beyond 80 km, so the event is kept (the error is subtracted once).
        (10, 54.96, -3.19, False, True),
        # 9 bits at London (535 km): far beyond both thresholds whatever the error, so both events are raised.
        (9, 51.5, -0.12, True, True),
    ],
)
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=80.0,
)
def test_uncertainty_suppresses_only_events_it_could_explain(
    bits,
    lat,
    lon,
    expect_cluster,
    expect_direct,
    create_managed_node,
    create_packet_observation,
    create_user,
    create_position_packet,
):
    observer = create_managed_node(
        meshtastic_node_id=0xE2000041,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    _run_position_at(
        observer=observer,
        create_packet_observation=create_packet_observation,
        create_user=create_user,
        create_position_packet=create_position_packet,
        packet_id=940002,
        remote_id=0xBEEF0241,
        bits=bits,
        lat=lat,
        lon=lon,
    )
    cluster = DxEvent.objects.filter(reason_code=DxReasonCode.NEW_DISTANT_NODE)
    direct = DxEvent.objects.filter(reason_code=DxReasonCode.DISTANT_OBSERVATION)
    assert cluster.exists() is expect_cluster
    assert direct.exists() is expect_direct
    expected_uncertainty = position_uncertainty_km(bits)
    for events in (cluster, direct):
        for event in events:
            metadata = DxEventObservation.objects.get(event=event).metadata
            assert metadata["uncertainty_km"] == pytest.approx(expected_uncertainty)


def _set_node_coords_bits(observed_node: ObservedNode, lat: float, lon: float, bits: int | None) -> None:
    NodeLatestStatus.objects.update_or_create(
        node=observed_node,
        defaults={"latitude": lat, "longitude": lon, "meshtastic_precision_bits": bits},
    )


def _complete_traceroute(
    source, packet_kwargs, create_traceroute_packet, create_packet_observation_for_tr, create_user
):
    packet = create_traceroute_packet(observer=source, **packet_kwargs)
    observation = create_packet_observation_for_tr(packet=packet, observer=source)
    with patch("traceroute.tasks.push_traceroute_to_neo4j"):
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            TraceroutePacketService().process_packet(packet, source, observation, create_user())


TR_SETTINGS = dict(DX_MONITORING_DETECTION_ENABLED=True, DX_MONITORING_TRACEROUTE_HOP_DISTANCE_KM=150.0)


@pytest.mark.django_db
@override_settings(**TR_SETTINGS)
def test_traceroute_hop_certainly_far_still_raises_with_uncertainty(
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    """A relay in London (535 km, 9 bits) is far whatever the error: the event is kept and carries the uncertainty."""
    source = create_managed_node(
        meshtastic_node_id=0xE2000042,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    target = create_observed_node(meshtastic_node_id=0xBEEF0242)
    relay = create_observed_node(meshtastic_node_id=0xCAFE0242)
    _set_node_coords_bits(target, 55.96, -3.20, 32)
    _set_node_coords_bits(relay, 51.5, -0.12, 9)
    _complete_traceroute(
        source,
        dict(
            from_int=target.meshtastic_node_id,
            route=[],
            route_back=[relay.meshtastic_node_id],
            snr_towards=[],
            snr_back=[-4.0],
        ),
        create_traceroute_packet,
        create_packet_observation_for_tr,
        create_user,
    )
    event = DxEvent.objects.get(reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP, destination=relay)
    assert DxEventObservation.objects.get(event=event).metadata["uncertainty_km"] == pytest.approx(
        position_uncertainty_km(9)
    )


@pytest.mark.django_db
@pytest.mark.parametrize("relay_bits,expect_event", [(9, False), (15, True)])
@override_settings(**TR_SETTINGS)
def test_traceroute_hop_with_coarse_end_as_first_or_second_node(
    relay_bits,
    expect_event,
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    """The relay sits 160 km from both the source and the target: it is the second node of one hop and the first of
    the next. At 9 bits (46.7 km) 160 km could really be under 150 km, so neither hop raises; at 15 bits both do."""
    source = create_managed_node(
        meshtastic_node_id=0xE2000043,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    target = create_observed_node(meshtastic_node_id=0xBEEF0243)
    relay = create_observed_node(meshtastic_node_id=0xCAFE0243)
    _set_node_coords_bits(target, 55.96, -3.20, 32)
    _set_node_coords_bits(relay, 54.51, -3.19, relay_bits)
    _complete_traceroute(
        source,
        dict(
            from_int=target.meshtastic_node_id,
            route=[relay.meshtastic_node_id],
            route_back=[],
            snr_towards=[-4.0],
            snr_back=[],
        ),
        create_traceroute_packet,
        create_packet_observation_for_tr,
        create_user,
    )
    hops = DxEvent.objects.filter(reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP)
    assert hops.filter(destination=relay).exists() is expect_event  # source -> relay
    assert hops.filter(destination=target).exists() is expect_event  # relay -> target


@pytest.mark.django_db
@override_settings(**TR_SETTINGS)
def test_traceroute_managed_source_counts_as_exact_not_its_observed_status_bits(
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    """The managed source's position is its owner-entered location. Even if its observed status says 9 bits, the
    160 km hop to an exact relay is certainly beyond 150 km."""
    source = create_managed_node(
        meshtastic_node_id=0xE2000044,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    source_observed = create_observed_node(meshtastic_node_id=source.meshtastic_node_id)
    _set_node_coords_bits(source_observed, 55.95, -3.19, 9)
    target = create_observed_node(meshtastic_node_id=0xBEEF0244)
    relay = create_observed_node(meshtastic_node_id=0xCAFE0244)
    _set_node_coords_bits(target, 55.96, -3.20, 32)
    _set_node_coords_bits(relay, 54.51, -3.19, 32)
    _complete_traceroute(
        source,
        dict(
            from_int=target.meshtastic_node_id,
            route=[relay.meshtastic_node_id],
            route_back=[],
            snr_towards=[-4.0],
            snr_back=[],
        ),
        create_traceroute_packet,
        create_packet_observation_for_tr,
        create_user,
    )
    event = DxEvent.objects.get(reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP, destination=relay)
    assert "uncertainty_km" not in DxEventObservation.objects.get(event=event).metadata


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_DETECTION_ENABLED=True,
    DX_MONITORING_CLUSTER_DISTANCE_KM=150.0,
    DX_MONITORING_DIRECT_DISTANCE_KM=80.0,
)
def test_nodedb_upsert_without_bits_keeps_coarse_precision_and_raises_no_false_event(
    create_managed_node,
    create_observed_node,
    create_user,
    create_message_packet,
    create_packet_observation,
):
    """A 9-bit node about 100 km away (46.7 km of uncertainty), then a NodeDB upsert 1 km away with no bits: the
    stored 9 bits stay, so a direct packet from it is not reported as a distant observation."""
    from django.utils import timezone

    from packets.serializers import NodeSerializer

    observer = create_managed_node(
        meshtastic_node_id=0xE2000045,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    node = create_observed_node(meshtastic_node_id=0xBEEF0245)
    _set_node_coords_bits(node, 55.05, -3.19, 9)
    serializer = NodeSerializer(
        instance=node,
        data={
            "id": node.meshtastic_node_id,
            "position": {
                "reported_time": timezone.now().isoformat(),
                "latitude": 55.04,  # about 1 km from the stored position
                "longitude": -3.19,
                "altitude": 5.0,
                "meshtastic_location_source": "UNSET",
            },
        },
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    assert NodeLatestStatus.objects.get(node=node).meshtastic_precision_bits == 9

    from dx_monitoring.services import maybe_detect_dx_candidate

    packet = create_message_packet(
        packet_id=940045,
        from_int=node.meshtastic_node_id,
        from_str=meshtastic_id_to_hex(node.meshtastic_node_id),
    )
    packet.first_reported_time = timezone.now()
    packet.save(update_fields=["first_reported_time"])
    observation = create_packet_observation(packet=packet, observer=observer)
    maybe_detect_dx_candidate(
        packet=packet,
        observer=observer,
        observation=observation,
        from_node=node,
        previous_last_heard=None,
    )
    assert not DxEvent.objects.filter(reason_code=DxReasonCode.DISTANT_OBSERVATION).exists()


@pytest.mark.django_db
@override_settings(**TR_SETTINGS)
def test_traceroute_hop_uncertainty_is_the_sum_of_both_ends_not_the_larger(
    create_managed_node,
    create_observed_node,
    create_user,
    create_traceroute_packet,
    create_packet_observation_for_tr,
):
    """Relay and target both at 10 bits (23.3 km each) and 190 km apart against a 150 km threshold. The two errors
    can oppose, so the sum (46.7 km) leaves 143 km: suppressed. Using only the larger (23.3 km) would raise."""
    source = create_managed_node(
        meshtastic_node_id=0xE2000046,
        default_location_latitude=55.95,
        default_location_longitude=-3.19,
    )
    target = create_observed_node(meshtastic_node_id=0xBEEF0246)
    relay = create_observed_node(meshtastic_node_id=0xCAFE0246)
    _set_node_coords_bits(relay, 54.51, -3.19, 10)  # 160 km from the source: 136.7 km after its own error
    _set_node_coords_bits(target, 56.22, -3.19, 10)  # 190 km from the relay
    _complete_traceroute(
        source,
        dict(
            from_int=target.meshtastic_node_id,
            route=[relay.meshtastic_node_id],
            route_back=[],
            snr_towards=[-4.0],
            snr_back=[],
        ),
        create_traceroute_packet,
        create_packet_observation_for_tr,
        create_user,
    )
    assert not DxEvent.objects.filter(reason_code=DxReasonCode.TRACEROUTE_DISTANT_HOP).exists()
