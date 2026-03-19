"""Tests for packet_received receiver that updates inferred_max_hops."""

import pytest

from constellations.models import MessageChannel
from nodes.models import NodeLatestStatus, ObservedNode
from packets.models import PacketObservation
from packets.signals import packet_received


@pytest.mark.django_db
def test_packet_received_sets_inferred_max_hops_for_message_packet(create_managed_node, create_message_packet):
    """When packet_received fires for MessagePacket, NodeLatestStatus.inferred_max_hops is set."""
    observer = create_managed_node()
    packet = create_message_packet(from_int=0x12345678, from_str="!12345678")
    channel = MessageChannel.objects.create(
        name="Test Channel",
        constellation=observer.constellation,
    )
    observation = PacketObservation.objects.create(
        packet=packet,
        observer=observer,
        channel=channel,
        hop_limit=5,
        hop_start=5,
        rx_time=packet.first_reported_time,
    )

    assert not ObservedNode.objects.filter(node_id=0x12345678).exists()

    packet_received.send(sender=None, packet=packet, observer=observer, observation=observation)

    observed_node = ObservedNode.objects.get(node_id=0x12345678)
    node_status = NodeLatestStatus.objects.get(node=observed_node)
    assert node_status.inferred_max_hops == 5


@pytest.mark.django_db
def test_packet_received_updates_inferred_max_hops_when_different(create_managed_node, create_message_packet):
    """When hop_start differs from stored value, inferred_max_hops is updated."""
    observer = create_managed_node()
    packet = create_message_packet(from_int=0xABCDEF12, from_str="!abcdef12")
    channel = MessageChannel.objects.create(
        name="Test Channel",
        constellation=observer.constellation,
    )
    observation = PacketObservation.objects.create(
        packet=packet,
        observer=observer,
        channel=channel,
        hop_limit=3,
        hop_start=3,
        rx_time=packet.first_reported_time,
    )

    packet_received.send(sender=None, packet=packet, observer=observer, observation=observation)
    node_status = NodeLatestStatus.objects.get(node__node_id=0xABCDEF12)
    assert node_status.inferred_max_hops == 3

    observation.hop_start = 7
    observation.save(update_fields=["hop_start"])
    packet_received.send(sender=None, packet=packet, observer=observer, observation=observation)

    node_status.refresh_from_db()
    assert node_status.inferred_max_hops == 7


@pytest.mark.django_db
def test_packet_received_skips_when_hop_start_is_none(create_managed_node, create_message_packet):
    """When observation.hop_start is None, receiver returns early and does not create NodeLatestStatus."""
    observer = create_managed_node()
    packet = create_message_packet(from_int=0x99999999, from_str="!99999999")
    channel = MessageChannel.objects.create(
        name="Test Channel",
        constellation=observer.constellation,
    )
    observation = PacketObservation.objects.create(
        packet=packet,
        observer=observer,
        channel=channel,
        hop_limit=None,
        hop_start=None,
        rx_time=packet.first_reported_time,
    )

    packet_received.send(sender=None, packet=packet, observer=observer, observation=observation)

    # Receiver returns early when hop_start is None, so NodeLatestStatus is never created
    assert not NodeLatestStatus.objects.filter(node__node_id=0x99999999).exists()
