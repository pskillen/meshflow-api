"""Tests for traceroute packet receiver (inferred AutoTraceRoute, late response)."""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401 - load fixtures
import users.tests.conftest  # noqa: F401 - load fixtures
from nodes.models import ObservedNode
from packets.models import PacketObservation, TraceroutePacket
from packets.signals import traceroute_packet_received
from traceroute.models import AutoTraceRoute


@pytest.fixture
def create_auto_traceroute(create_managed_node, create_observed_node, create_user):
    """Create an AutoTraceRoute for testing."""

    def make_auto_traceroute(**kwargs):
        if "source_node" not in kwargs:
            kwargs["source_node"] = create_managed_node()
        if "target_node" not in kwargs:
            kwargs["target_node"] = create_observed_node()
        if "trigger_type" not in kwargs:
            kwargs["trigger_type"] = AutoTraceRoute.TRIGGER_TYPE_USER
        if "triggered_by" not in kwargs:
            kwargs["triggered_by"] = create_user()
        if "status" not in kwargs:
            kwargs["status"] = AutoTraceRoute.STATUS_COMPLETED
        return AutoTraceRoute.objects.create(**kwargs)

    return make_auto_traceroute


@pytest.fixture
def create_traceroute_packet(create_managed_node):
    """Create a TraceroutePacket with route data."""

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
    """Create PacketObservation for a traceroute packet."""

    def make_observation(packet=None, observer=None, **kwargs):
        from constellations.models import MessageChannel

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


@pytest.mark.django_db
def test_traceroute_receiver_inferred_creation(
    create_traceroute_packet, create_managed_node, create_packet_observation_for_tr
):
    """When no AutoTraceRoute exists, an inferred one is created."""
    source_node = create_managed_node()
    target_node_id = 0xABCDEF12
    packet = create_traceroute_packet(
        observer=source_node,
        from_int=target_node_id,
        route=[0x11111111],
        route_back=[0x11111111],
        snr_towards=[-5.0],
        snr_back=[-4.0],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source_node)

    assert not AutoTraceRoute.objects.filter(source_node=source_node, target_node__node_id=target_node_id).exists()
    assert not ObservedNode.objects.filter(node_id=target_node_id).exists()

    with patch("traceroute.tasks.push_traceroute_to_neo4j") as mock_push:
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            traceroute_packet_received.send(sender=None, packet=packet, observer=source_node, observation=observation)

    auto_tr = AutoTraceRoute.objects.get(source_node=source_node, target_node__node_id=target_node_id)
    assert auto_tr.trigger_type == AutoTraceRoute.TRIGGER_TYPE_EXTERNAL
    assert auto_tr.triggered_by is None
    assert auto_tr.status == AutoTraceRoute.STATUS_COMPLETED
    assert auto_tr.raw_packet_id == packet.id
    assert auto_tr.route == [{"node_id": 0x11111111, "snr": -5.0}]
    assert auto_tr.route_back == [{"node_id": 0x11111111, "snr": -4.0}]

    target_node = ObservedNode.objects.get(node_id=target_node_id)
    assert target_node.node_id_str == "!abcdef12"
    mock_push.delay.assert_called_once_with(auto_tr.id)


@pytest.mark.django_db
def test_traceroute_receiver_snr_mapping_route_longer_than_snr(
    create_traceroute_packet, create_managed_node, create_packet_observation_for_tr
):
    """When route is longer than snr_towards, extra nodes get snr: None (1:1 mapping, no index error)."""
    source_node = create_managed_node()
    target_node_id = 0xABCDEF12
    packet = create_traceroute_packet(
        observer=source_node,
        from_int=target_node_id,
        route=[0x11111111, 0x22222222, 0x33333333],
        route_back=[0x33333333, 0x22222222, 0x11111111],
        snr_towards=[-5.0, -3.0],  # Only 2 values for 3 route nodes
        snr_back=[-4.0, -2.0],  # Only 2 values for 3 route_back nodes
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source_node)

    with patch("traceroute.tasks.push_traceroute_to_neo4j"):
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            traceroute_packet_received.send(sender=None, packet=packet, observer=source_node, observation=observation)

    auto_tr = AutoTraceRoute.objects.get(source_node=source_node, target_node__node_id=target_node_id)
    assert auto_tr.route == [
        {"node_id": 0x11111111, "snr": -5.0},
        {"node_id": 0x22222222, "snr": -3.0},
        {"node_id": 0x33333333, "snr": None},
    ]
    assert auto_tr.route_back == [
        {"node_id": 0x33333333, "snr": -4.0},
        {"node_id": 0x22222222, "snr": -2.0},
        {"node_id": 0x11111111, "snr": None},
    ]


@pytest.mark.django_db
def test_traceroute_receiver_late_response_updates_failed(
    create_traceroute_packet,
    create_managed_node,
    create_observed_node,
    create_auto_traceroute,
    create_packet_observation_for_tr,
):
    """When a failed AutoTraceRoute exists within 5 mins, late response updates it to completed."""
    source_node = create_managed_node()
    target_node = create_observed_node(node_id=0xDEADBEEF)
    auto_tr = create_auto_traceroute(
        source_node=source_node,
        target_node=target_node,
        status=AutoTraceRoute.STATUS_FAILED,
        triggered_by=None,
    )
    auto_tr.triggered_at = timezone.now() - timedelta(minutes=2)
    auto_tr.save(update_fields=["triggered_at"])

    packet = create_traceroute_packet(
        observer=source_node,
        from_int=target_node.node_id,
        route=[0x11111111],
        route_back=[0x11111111],
        snr_towards=[-5.0],
        snr_back=[-4.0],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source_node)

    initial_count = AutoTraceRoute.objects.count()

    with patch("traceroute.tasks.push_traceroute_to_neo4j") as mock_push:
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            traceroute_packet_received.send(sender=None, packet=packet, observer=source_node, observation=observation)

    assert AutoTraceRoute.objects.count() == initial_count
    auto_tr.refresh_from_db()
    assert auto_tr.status == AutoTraceRoute.STATUS_COMPLETED
    assert auto_tr.trigger_type != AutoTraceRoute.TRIGGER_TYPE_EXTERNAL  # Original record, not external
    assert auto_tr.raw_packet_id == packet.id
    assert auto_tr.error_message is None
    mock_push.delay.assert_called_once_with(auto_tr.id)


@pytest.mark.django_db
def test_traceroute_receiver_external_inferred_empty_routes_completed(
    create_traceroute_packet, create_managed_node, create_packet_observation_for_tr
):
    """Direct path (no relay hops): external inferred AutoTraceRoute is completed, not failed."""
    source_node = create_managed_node()
    target_node_id = 0xABCDEF12
    packet = create_traceroute_packet(
        observer=source_node,
        from_int=target_node_id,
        route=[],
        route_back=[],
        snr_towards=[],
        snr_back=[],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source_node)

    with patch("traceroute.tasks.push_traceroute_to_neo4j") as mock_push:
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            traceroute_packet_received.send(sender=None, packet=packet, observer=source_node, observation=observation)

    auto_tr = AutoTraceRoute.objects.get(source_node=source_node, target_node__node_id=target_node_id)
    assert auto_tr.trigger_type == AutoTraceRoute.TRIGGER_TYPE_EXTERNAL
    assert auto_tr.status == AutoTraceRoute.STATUS_COMPLETED
    assert auto_tr.route == []
    assert auto_tr.route_back == []
    assert auto_tr.error_message is None
    mock_push.delay.assert_called_once_with(auto_tr.id)


@pytest.mark.django_db
def test_traceroute_receiver_late_response_empty_routes_updates_failed_to_completed(
    create_traceroute_packet,
    create_managed_node,
    create_observed_node,
    create_auto_traceroute,
    create_packet_observation_for_tr,
):
    """Late response with empty route/route_back clears error_message and completes."""
    source_node = create_managed_node()
    target_node = create_observed_node(node_id=0xCAFEBABE)
    auto_tr = create_auto_traceroute(
        source_node=source_node,
        target_node=target_node,
        status=AutoTraceRoute.STATUS_FAILED,
        error_message="Timed out after 180s",
        triggered_by=None,
    )
    auto_tr.triggered_at = timezone.now() - timedelta(minutes=2)
    auto_tr.save(update_fields=["triggered_at", "error_message"])

    packet = create_traceroute_packet(
        observer=source_node,
        from_int=target_node.node_id,
        route=[],
        route_back=[],
        snr_towards=[],
        snr_back=[],
    )
    observation = create_packet_observation_for_tr(packet=packet, observer=source_node)

    with patch("traceroute.tasks.push_traceroute_to_neo4j"):
        with patch("traceroute.ws_notify.notify_traceroute_status_changed"):
            traceroute_packet_received.send(sender=None, packet=packet, observer=source_node, observation=observation)

    auto_tr.refresh_from_db()
    assert auto_tr.status == AutoTraceRoute.STATUS_COMPLETED
    assert auto_tr.error_message is None
    assert auto_tr.route == []
    assert auto_tr.route_back == []
