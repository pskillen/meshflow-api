"""Tests for MeshCoreTextMessageService."""

from django.utils import timezone

import pytest

from common.protocol import Protocol
from meshcore_packets.models import MeshCorePayloadType, MeshCoreTextPacket
from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.services.text_message import MeshCoreTextMessageService
from text_messages.models import TextMessage


@pytest.mark.django_db
def test_channel_text_creates_broadcast_message(meshcore_feeder):
    node = meshcore_feeder["node"]
    reconcile_mc_channels(
        node,
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    now = timezone.now()
    packet = MeshCoreTextPacket.objects.create(
        observer=node,
        payload_type=MeshCorePayloadType.CHANNEL_TEXT,
        event_type="channel_message",
        rx_time=now,
        raw_json={},
        text="hello mesh",
        channel=node.mc_channels.first(),
    )
    from meshcore_packets.models import MeshCorePacketObservation

    obs = MeshCorePacketObservation.objects.create(
        packet=packet,
        observer=node,
        channel=packet.channel,
        rx_time=now,
    )
    msg = MeshCoreTextMessageService().process_packet(packet, node, obs)
    assert msg is not None
    assert msg.protocol == Protocol.MESHCORE
    assert msg.sender_id is None
    assert msg.message_text == "hello mesh"
    assert TextMessage.objects.filter(original_mc_packet=packet).count() == 1

    dup = MeshCoreTextMessageService().process_packet(packet, node, obs)
    assert dup is None


@pytest.mark.django_db
def test_contact_text_stores_with_sender_prefix(meshcore_feeder):
    node = meshcore_feeder["node"]
    now = timezone.now()
    packet = MeshCoreTextPacket.objects.create(
        observer=node,
        payload_type=MeshCorePayloadType.CONTACT_TEXT,
        event_type="contact_message",
        from_pubkey_prefix="aabbccddeeff",
        rx_time=now,
        raw_json={},
        text="dm hello",
    )
    from meshcore_packets.models import MeshCorePacketObservation

    obs = MeshCorePacketObservation.objects.create(packet=packet, observer=node, rx_time=now)
    msg = MeshCoreTextMessageService().process_packet(packet, node, obs)
    assert msg.sender_id is not None
    assert msg.channel_id is None
