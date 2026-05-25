"""Tests for MeshCoreTextMessageService."""

from django.utils import timezone

import pytest

from common.protocol import Protocol
from meshcore_packets.models import MeshCorePayloadType, MeshCoreTextPacket
from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.services.text_message import MeshCoreTextMessageService
from nodes.models import NodeOwnerClaim, ObservedNode
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


@pytest.mark.django_db
def test_contact_text_accepts_node_claim(meshcore_feeder, create_user):
    user = create_user()
    prefix = "aabbccddeeff"
    sender = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey_prefix=prefix,
        long_name="Claim Me",
        short_name="CLM",
        last_heard=timezone.now(),
    )
    claim_key = "word word 42"
    NodeOwnerClaim.objects.create(node=sender, user=user, claim_key=claim_key, accepted_at=None)

    feeder = meshcore_feeder["node"]
    now = timezone.now()
    packet = MeshCoreTextPacket.objects.create(
        observer=feeder,
        payload_type=MeshCorePayloadType.CONTACT_TEXT,
        event_type="contact_message",
        from_pubkey_prefix=prefix,
        rx_time=now,
        raw_json={},
        text=claim_key,
    )
    from meshcore_packets.models import MeshCorePacketObservation

    obs = MeshCorePacketObservation.objects.create(packet=packet, observer=feeder, rx_time=now)
    MeshCoreTextMessageService().process_packet(packet, feeder, obs)

    sender.refresh_from_db()
    assert sender.claimed_by_id == user.id


@pytest.mark.django_db
def test_channel_text_does_not_accept_node_claim(meshcore_feeder, create_user, create_observed_node):
    user = create_user()
    node = create_observed_node(
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey_prefix="bbccddeeff00",
        last_heard=timezone.now(),
    )
    claim_key = "word word 99"
    NodeOwnerClaim.objects.create(node=node, user=user, claim_key=claim_key, accepted_at=None)

    feeder_node = meshcore_feeder["node"]
    reconcile_mc_channels(
        feeder_node,
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    now = timezone.now()
    packet = MeshCoreTextPacket.objects.create(
        observer=feeder_node,
        payload_type=MeshCorePayloadType.CHANNEL_TEXT,
        event_type="channel_message",
        rx_time=now,
        raw_json={},
        text=claim_key,
        channel=feeder_node.mc_channels.first(),
    )
    from meshcore_packets.models import MeshCorePacketObservation

    obs = MeshCorePacketObservation.objects.create(
        packet=packet,
        observer=feeder_node,
        channel=packet.channel,
        rx_time=now,
    )
    MeshCoreTextMessageService().process_packet(packet, feeder_node, obs)

    node.refresh_from_db()
    assert node.claimed_by_id is None
