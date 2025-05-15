import pytest

from packets.services.device_metrics import DeviceMetricsPacketService
from packets.services.factory import PacketServiceFactory
from packets.services.node_info import NodeInfoPacketService
from packets.services.position import PositionPacketService
from packets.services.text_message import TextMessagePacketService


@pytest.mark.django_db
def test_create_service_position_packet(create_position_packet):
    """Test creating a service for a position packet."""
    packet = create_position_packet()
    service = PacketServiceFactory.create_service(packet)
    assert isinstance(service, PositionPacketService)


@pytest.mark.django_db
def test_create_service_device_metrics_packet(create_device_metrics_packet):
    """Test creating a service for a device metrics packet."""
    packet = create_device_metrics_packet()
    service = PacketServiceFactory.create_service(packet)
    assert isinstance(service, DeviceMetricsPacketService)


@pytest.mark.django_db
def test_create_service_message_packet(create_message_packet):
    """Test creating a service for a message packet."""
    packet = create_message_packet()
    service = PacketServiceFactory.create_service(packet)
    assert isinstance(service, TextMessagePacketService)


@pytest.mark.django_db
def test_create_service_node_info_packet(create_node_info_packet):
    """Test creating a service for a node info packet."""
    packet = create_node_info_packet()
    service = PacketServiceFactory.create_service(packet)
    assert isinstance(service, NodeInfoPacketService)


@pytest.mark.django_db
def test_create_service_raw_packet(create_raw_packet):
    """Test creating a service for a raw packet."""
    packet = create_raw_packet()
    service = PacketServiceFactory.create_service(packet)
    assert service is None
