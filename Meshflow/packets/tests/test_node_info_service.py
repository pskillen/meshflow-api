import pytest

from nodes.models import ObservedNode
from packets.models import RoleSource
from packets.services.node_info import NodeInfoPacketService


@pytest.mark.django_db
def test_node_info_service_init():
    """Test NodeInfoPacketService initialization."""
    service = NodeInfoPacketService()
    assert isinstance(service, NodeInfoPacketService)


@pytest.mark.django_db
def test_process_packet_invalid_type(create_raw_packet, create_managed_node, create_packet_observation, create_user):
    """Test processing a packet with an invalid type."""
    service = NodeInfoPacketService()
    packet = create_raw_packet()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    # This should raise a ValueError due to type check
    with pytest.raises(ValueError, match="Packet must be a NodeInfoPacket"):
        service.process_packet(packet, observer, observation, user)


@pytest.mark.django_db
def test_process_node_info_packet_same_node(
    create_node_info_packet, create_managed_node, create_packet_observation, create_user
):
    """Test processing a node info packet for the same node."""
    service = NodeInfoPacketService()

    # Create a packet where the node_id matches the from_int
    packet = create_node_info_packet(node_id="!3ade68b1")
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    # Create the from_node with different attributes, matching node_id as integer
    from_node = ObservedNode.objects.get_or_create(node_id=packet.from_int)[0]
    from_node.short_name = "OLD_NAME"
    from_node.long_name = "Old Name"
    from_node.hw_model = "Old Model"
    from_node.sw_version = "1.0.0"
    from_node.role = RoleSource.CLIENT
    from_node.save()

    # Process the packet
    service.process_packet(packet, observer, observation, user)

    # Verify the node was updated
    from_node.refresh_from_db()
    assert from_node.short_name == packet.short_name
    assert from_node.long_name == packet.long_name
    assert from_node.hw_model == packet.hw_model
    assert from_node.sw_version == packet.sw_version
    assert from_node.role == packet.role


@pytest.mark.django_db
def test_process_node_info_packet_different_node(
    create_node_info_packet, create_managed_node, create_packet_observation, create_user
):
    """Test processing a node info packet for a different node."""
    service = NodeInfoPacketService()

    # Create a packet where the node_id is different from the from_int
    packet = create_node_info_packet(node_id="!different")
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    # Create the from_node with different attributes
    from_node = ObservedNode.objects.get_or_create(node_id=packet.from_int)[0]
    from_node.short_name = "OLD_NAME"
    from_node.long_name = "Old Name"
    from_node.hw_model = "Old Model"
    from_node.sw_version = "1.0.0"
    from_node.role = RoleSource.CLIENT
    from_node.save()

    # Process the packet
    service.process_packet(packet, observer, observation, user)

    # Verify the node was updated
    from_node.refresh_from_db()
    assert from_node.short_name == packet.short_name
    assert from_node.long_name == packet.long_name
    assert from_node.hw_model == packet.hw_model
    assert from_node.sw_version == packet.sw_version
    assert from_node.role == packet.role
