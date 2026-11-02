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
    from_node = ObservedNode.objects.get_or_create(meshtastic_node_id=packet.from_int)[0]
    from_node.short_name = "OLD_NAME"
    from_node.long_name = "Old Name"
    from_node.meshtastic_hw_model = "Old Model"
    from_node.meshtastic_role = RoleSource.CLIENT
    from_node.save()

    # Process the packet
    service.process_packet(packet, observer, observation, user)

    # Verify the node was updated
    from_node.refresh_from_db()
    assert from_node.short_name == packet.short_name
    assert from_node.long_name == packet.long_name
    assert from_node.meshtastic_hw_model == packet.hw_model
    assert from_node.meshtastic_role == packet.role
    assert from_node.meshtastic_public_key == packet.public_key
    assert from_node.mac_addr == packet.mac_address
    assert from_node.meshtastic_is_licensed == packet.is_licensed
    assert from_node.meshtastic_is_unmessagable == packet.is_unmessagable


@pytest.mark.django_db
def test_node_info_packet_does_not_clobber_identity(
    create_node_info_packet, create_managed_node, create_packet_observation, create_user
):
    """A 2.8-shaped NodeInfo (zero MAC, no key, 24-byte name) leaves stored identity data intact."""
    long_name = "Highland Ridge Repeater North-East"
    key = "oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs="
    key_hex = "a0b3a9cf5a7b5bcfd38bc67488e5384ea6406150177b75309bc105fe6d732c5b"
    packet = create_node_info_packet(
        node_id="!3ade68b1",
        long_name=long_name.encode()[:24].decode(),
        mac_address="00:00:00:00:00:00",
        public_key=None,
    )
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    from_node = ObservedNode.objects.get_or_create(meshtastic_node_id=packet.from_int)[0]
    from_node.long_name = long_name
    from_node.mac_addr = "a0:b3:a9:cf:5a:7b"
    from_node.meshtastic_public_key = key
    from_node.meshtastic_public_key_hex = key_hex
    from_node.meshtastic_key_node_id = 0x4396524C
    from_node.save()

    NodeInfoPacketService().process_packet(packet, observer, observation, create_user())

    from_node.refresh_from_db()
    assert from_node.long_name == long_name
    assert from_node.mac_addr == "a0:b3:a9:cf:5a:7b"
    assert from_node.meshtastic_public_key == key
    assert from_node.meshtastic_public_key_hex == key_hex
    assert from_node.meshtastic_key_node_id == 0x4396524C


@pytest.mark.django_db
def test_process_node_info_packet_different_node(
    create_node_info_packet, create_managed_node, create_packet_observation, create_user
):
    """Test processing a node info packet for a different node (node_id != from_int)."""
    service = NodeInfoPacketService()

    # Create a packet where the node_id is different from the from_int
    packet = create_node_info_packet(node_id="!different")
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    # Create the from_node with different attributes
    from_node = ObservedNode.objects.get_or_create(meshtastic_node_id=packet.from_int)[0]
    from_node.short_name = "OLD_NAME"
    from_node.long_name = "Old Name"
    from_node.meshtastic_hw_model = "Old Model"
    from_node.meshtastic_role = RoleSource.CLIENT
    from_node.save()

    # Process the packet
    service.process_packet(packet, observer, observation, user)

    # Verify the node was updated
    from_node.refresh_from_db()
    assert from_node.short_name == packet.short_name
    assert from_node.long_name == packet.long_name
    assert from_node.meshtastic_hw_model == packet.hw_model
    assert from_node.meshtastic_role == packet.role
    assert from_node.meshtastic_public_key == packet.public_key
    assert from_node.mac_addr == packet.mac_address
    assert from_node.meshtastic_is_licensed == packet.is_licensed
    assert from_node.meshtastic_is_unmessagable == packet.is_unmessagable


@pytest.mark.django_db
def test_process_node_info_packet_sets_predicted_node_id(
    create_node_info_packet, create_managed_node, create_packet_observation, create_user
):
    """The packet key is normalised to hex and the predicted 2.8 id (crc32) is stored."""
    packet = create_node_info_packet(public_key="oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs=")
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    from_node = ObservedNode.objects.get_or_create(meshtastic_node_id=packet.from_int)[0]

    NodeInfoPacketService().process_packet(packet, observer, observation, create_user())

    from_node.refresh_from_db()
    assert from_node.meshtastic_public_key_hex == "a0b3a9cf5a7b5bcfd38bc67488e5384ea6406150177b75309bc105fe6d732c5b"
    assert from_node.meshtastic_key_node_id == 0x4396524C


@pytest.mark.django_db
def test_process_node_info_packet_malformed_key_gives_null_prediction(
    create_node_info_packet, create_managed_node, create_packet_observation, create_user
):
    packet = create_node_info_packet(public_key="not-a-32-byte-key")
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    from_node = ObservedNode.objects.get_or_create(meshtastic_node_id=packet.from_int)[0]

    NodeInfoPacketService().process_packet(packet, observer, observation, create_user())

    from_node.refresh_from_db()
    assert from_node.meshtastic_public_key_hex is None
    assert from_node.meshtastic_key_node_id is None
