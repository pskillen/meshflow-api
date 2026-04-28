"""Fixtures for DX monitoring tests (traceroute helpers aligned with packets tests)."""

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from constellations.models import MessageChannel
from packets.models import PacketObservation, TraceroutePacket
from traceroute.tests.factories import make_auto_traceroute


@pytest.fixture
def create_auto_traceroute(create_managed_node, create_observed_node, create_user):
    def _create(**kwargs):
        return make_auto_traceroute(
            create_managed_node,
            create_observed_node,
            create_user,
            **kwargs,
        )

    return _create


@pytest.fixture
def create_traceroute_packet(create_managed_node):
    def make_packet(observer=None, from_int=0x12345678, route=None, route_back=None, **kwargs):
        if observer is None:
            observer = create_managed_node()
        if route is None:
            route = [0x11111111, 0x22222222]
        if route_back is None:
            route_back = [0x22222222, 0x11111111]
        snr_towards = kwargs.pop("snr_towards", [-5.0, -3.0])
        snr_back = kwargs.pop("snr_back", [-4.0, -2.0])
        node_id_str = f"!{from_int:08x}"
        packet = TraceroutePacket.objects.create(
            packet_id=kwargs.pop("packet_id", 999888777),
            from_int=from_int,
            from_str=node_id_str,
            to_int=observer.node_id,
            to_str=observer.node_id_str,
            port_num="TRACEROUTE_APP",
            route=route,
            route_back=route_back,
            snr_towards=snr_towards,
            snr_back=snr_back,
            **kwargs,
        )
        return packet

    return make_packet


@pytest.fixture
def create_packet_observation_for_tr(create_traceroute_packet, create_managed_node):
    def make_observation(packet=None, observer=None, **kwargs):
        if packet is None:
            observer = observer or create_managed_node()
            packet = create_traceroute_packet(observer=observer)
        if observer is None:
            observer = packet.observations.first().observer if packet.observations.exists() else create_managed_node()
        channel = MessageChannel.objects.create(
            name=f"Channel {observer.internal_id}",
            constellation=observer.constellation,
        )
        return PacketObservation.objects.create(
            packet=packet,
            observer=observer,
            channel=channel,
            hop_limit=3,
            hop_start=3,
            rx_time=timezone.now(),
            rx_rssi=-60.0,
            rx_snr=10.0,
            upload_time=timezone.now(),
            **kwargs,
        )

    return make_observation
