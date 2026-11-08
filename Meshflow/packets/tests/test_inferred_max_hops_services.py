"""Every service that used to write meshtastic_inferred_max_hops now goes through packets.hops."""

from django.utils import timezone

import pytest

from nodes.models import NodeLatestStatus
from packets.models import (
    AirQualityMetricsPacket,
    DeviceMetricsPacket,
    EnvironmentMetricsPacket,
    HealthMetricsPacket,
    HostMetricsPacket,
    PositionPacket,
    PowerMetricsPacket,
)
from packets.services.air_quality import AirQualityMetricsPacketService
from packets.services.device_metrics import DeviceMetricsPacketService
from packets.services.environment_metrics import EnvironmentMetricsPacketService
from packets.services.health_metrics import HealthMetricsPacketService
from packets.services.host_metrics import HostMetricsPacketService
from packets.services.position import PositionPacketService
from packets.services.power_metrics import PowerMetricsPacketService

SERVICES = [
    (PositionPacketService, PositionPacket, "POSITION_APP"),
    (DeviceMetricsPacketService, DeviceMetricsPacket, "TELEMETRY_APP"),
    (EnvironmentMetricsPacketService, EnvironmentMetricsPacket, "TELEMETRY_APP"),
    (AirQualityMetricsPacketService, AirQualityMetricsPacket, "TELEMETRY_APP"),
    (PowerMetricsPacketService, PowerMetricsPacket, "TELEMETRY_APP"),
    (HealthMetricsPacketService, HealthMetricsPacket, "TELEMETRY_APP"),
    (HostMetricsPacketService, HostMetricsPacket, "TELEMETRY_APP"),
]


def make_packet(model, from_int, **extra):
    fields = {
        "packet_id": 4242,
        "from_int": from_int,
        "from_str": f"!{from_int:08x}",
        "to_int": 0xFFFFFFFF,
        "to_str": "!ffffffff",
        "port_num": "POSITION_APP" if model is PositionPacket else "TELEMETRY_APP",
    }
    if model is not PositionPacket:
        fields["reading_time"] = timezone.now()
    fields.update(extra)
    return model.objects.create(**fields)


@pytest.mark.django_db
@pytest.mark.parametrize("service_cls,packet_model,port", SERVICES)
def test_service_sets_inferred_max_hops_through_helper(
    service_cls, packet_model, port, create_managed_node, create_packet_observation, create_user
):
    observer = create_managed_node()
    packet = make_packet(packet_model, 0x1000ABCD)
    observation = create_packet_observation(packet=packet, observer=observer, hop_start=4, hop_limit=2)

    service_cls().process_packet(packet, observer, observation, create_user())

    status = NodeLatestStatus.objects.get(node__meshtastic_node_id=0x1000ABCD)
    assert status.meshtastic_inferred_max_hops == 4
    assert status.meshtastic_inferred_max_hops_source == port
    assert status.meshtastic_inferred_max_hops_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize("service_cls,packet_model,port", SERVICES)
def test_service_does_not_lower_value_set_by_text(
    service_cls, packet_model, port, create_managed_node, create_packet_observation, create_user
):
    """A scaled-port packet with a smaller hop_start leaves a fresh authoritative value alone (#449)."""
    observer = create_managed_node()
    packet = make_packet(packet_model, 0x2000ABCD)
    observation = create_packet_observation(packet=packet, observer=observer, hop_start=1, hop_limit=1)

    # First pass creates the node and status; then pretend text set 3.
    service_cls().process_packet(packet, observer, observation, create_user())
    NodeLatestStatus.objects.filter(node__meshtastic_node_id=0x2000ABCD).update(
        meshtastic_inferred_max_hops=3,
        meshtastic_inferred_max_hops_source="TEXT_MESSAGE_APP",
        meshtastic_inferred_max_hops_at=timezone.now(),
    )
    service_cls().process_packet(packet, observer, observation, create_user())

    status = NodeLatestStatus.objects.get(node__meshtastic_node_id=0x2000ABCD)
    assert status.meshtastic_inferred_max_hops == 3
    assert status.meshtastic_inferred_max_hops_source == "TEXT_MESSAGE_APP"
