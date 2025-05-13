from unittest.mock import patch

import pytest

from common.mesh_node_helpers import BROADCAST_ID
from constellations.models import MessageChannel
from nodes.models import NodeOwnerClaim, ObservedNode
from packets.services.text_message import TextMessagePacketService
from text_messages.models import TextMessage


@pytest.mark.django_db
def test_text_message_service_init():
    """Test TextMessagePacketService initialization."""
    service = TextMessagePacketService()
    assert isinstance(service, TextMessagePacketService)


@pytest.mark.django_db
def test_process_packet_invalid_type(create_raw_packet, create_managed_node, create_packet_observation, create_user):
    """Test processing a packet with an invalid type."""
    service = TextMessagePacketService()
    packet = create_raw_packet()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    with pytest.raises(ValueError, match="Packet must be a MessagePacket"):
        service.process_packet(packet, observer, observation, user)


@pytest.mark.django_db
def test_process_packet_already_processed(
    create_message_packet, create_managed_node, create_packet_observation, create_user
):
    """Test processing a packet that has already been processed."""
    service = TextMessagePacketService()
    packet = create_message_packet()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    # Create a message with the same packet_id to simulate already processed
    TextMessage.objects.create(
        packet_id=packet.packet_id,
        sender=ObservedNode.objects.get_or_create(node_id=packet.from_int)[0],
        original_packet=packet,
        recipient_node_id=packet.to_int,
        message_text=packet.message_text,
        is_emoji=packet.emoji,
    )

    # This should not raise an error, but also not create a new message
    initial_count = TextMessage.objects.count()
    service.process_packet(packet, observer, observation, user)
    assert TextMessage.objects.count() == initial_count


@pytest.mark.django_db
def test_create_message(create_message_packet, create_managed_node, create_packet_observation, create_user):
    """Test creating a message from a packet."""
    service = TextMessagePacketService()
    packet = create_message_packet()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    initial_count = TextMessage.objects.count()
    service.process_packet(packet, observer, observation, user)
    assert TextMessage.objects.count() == initial_count + 1

    message = TextMessage.objects.latest("id")
    assert message.sender.node_id == packet.from_int
    assert message.original_packet == packet
    assert message.recipient_node_id == packet.to_int
    assert message.message_text == packet.message_text
    assert message.is_emoji == packet.emoji
    assert message.reply_to_message_id == packet.reply_packet_id


@pytest.mark.django_db
def test_create_message_with_channel(
    create_message_packet, create_managed_node, create_packet_observation, create_user, create_constellation
):
    """Test creating a message with a channel."""
    service = TextMessagePacketService()
    packet = create_message_packet()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer, channel=1)
    user = create_user()

    # Create a real MessageChannel instance
    constellation = create_constellation()
    message_channel = MessageChannel.objects.create(name="test_channel", constellation=constellation)

    # Mock the get_channel method to return a MessageChannel instance
    with patch.object(observer, "get_channel", return_value=message_channel):
        service.process_packet(packet, observer, observation, user)

    message = TextMessage.objects.latest("id")
    assert message.channel == message_channel


@pytest.mark.django_db
def test_create_message_with_invalid_channel(
    create_message_packet, create_managed_node, create_packet_observation, create_user
):
    """Test creating a message with an invalid channel."""
    service = TextMessagePacketService()
    packet = create_message_packet()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer, channel=1)
    user = create_user()

    # Mock the get_channel method to raise ValueError
    with patch.object(observer, "get_channel", side_effect=ValueError):
        service.process_packet(packet, observer, observation, user)

    message = TextMessage.objects.latest("id")
    assert message.channel is None


@pytest.mark.django_db
def test_authorize_node_claim_broadcast_message(
    create_message_packet, create_managed_node, create_packet_observation, create_user
):
    """Test authorizing a node claim with a broadcast message."""
    service = TextMessagePacketService()
    packet = create_message_packet(to_int=BROADCAST_ID, to_str="!broadcast")
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    # This should not attempt to authorize a claim
    service.process_packet(packet, observer, observation, user)
    # No assertions needed, just making sure it doesn't raise an error


@pytest.mark.django_db
def test_authorize_node_claim_non_claim_message(
    create_message_packet, create_managed_node, create_packet_observation, create_user
):
    """Test authorizing a node claim with a message that doesn't match the claim key format."""
    service = TextMessagePacketService()
    packet = create_message_packet(message_text="This is not a claim key")
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    # This should not attempt to authorize a claim
    service.process_packet(packet, observer, observation, user)
    # No assertions needed, just making sure it doesn't raise an error


@pytest.mark.django_db
def test_authorize_node_claim_no_matching_claim(
    create_message_packet, create_managed_node, create_packet_observation, create_user
):
    """Test authorizing a node claim with no matching claim."""
    service = TextMessagePacketService()
    packet = create_message_packet(message_text="word word word 123")
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    # This should not find a matching claim
    service.process_packet(packet, observer, observation, user)
    # No assertions needed, just making sure it doesn't raise an error


@pytest.mark.django_db
def test_authorize_node_claim_success(
    create_message_packet, create_managed_node, create_packet_observation, create_user
):
    """Test successfully authorizing a node claim."""
    service = TextMessagePacketService()
    packet = create_message_packet(message_text="word word word 123")
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    user = create_user()

    # Create a node and a claim for it
    from_node = ObservedNode.objects.get_or_create(node_id=packet.from_int)[0]
    claim = NodeOwnerClaim.objects.create(
        node=from_node,
        user=user,
        claim_key="word word word 123",
        accepted_at=None,
    )

    # Process the packet
    service.process_packet(packet, observer, observation, user)

    # Verify the claim was accepted
    claim.refresh_from_db()
    assert claim.accepted_at is not None

    # Verify the node was claimed
    from_node.refresh_from_db()
    assert from_node.claimed_by == user
