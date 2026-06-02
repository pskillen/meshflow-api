"""Regression tests for canonical MC channels across feeders (#379)."""

from django.utils import timezone

import pytest

from common.protocol import Protocol
from constellations.models import MessageChannel
from meshcore_packets.models import MeshCorePacketObservation, MeshCorePayloadType, MeshCoreTextPacket
from meshcore_packets.services.channel import resolve_mc_channel
from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.services.dedup_key import channel_text_dedup_key
from meshcore_packets.services.text_message import MeshCoreTextMessageService
from nodes.models import NodeAuth
from text_messages.models import TextMessage


@pytest.mark.django_db
def test_two_feeders_same_hashtag_different_indices_one_canonical(
    meshcore_feeder, create_managed_node, create_node_api_key
):
    """Same logical hashtag on different device slots → one MessageChannel, two links."""
    constellation = meshcore_feeder["node"].constellation
    feeder_b = create_managed_node(
        meshtastic_node_id=None,
        protocol=Protocol.MESHCORE,
        name="MC Feeder B",
        mc_pubkey="c" * 64,
        constellation=constellation,
    )
    api_key_b = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key_b, node=feeder_b)

    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 1, "name": "test", "mc_channel_type": "HASHTAG", "mc_hashtag": "test"}],
    )
    reconcile_mc_channels(
        feeder_b,
        [{"mc_channel_idx": 2, "name": "test", "mc_channel_type": "HASHTAG", "mc_hashtag": "test"}],
    )

    canonical = MessageChannel.objects.filter(
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_hashtag="test",
    )
    assert canonical.count() == 1

    ch_a = resolve_mc_channel(meshcore_feeder["node"], 1)
    ch_b = resolve_mc_channel(feeder_b, 2)
    assert ch_a.id == ch_b.id


@pytest.mark.django_db
def test_two_feeders_ingest_same_text_same_channel_id(meshcore_feeder, create_managed_node, create_node_api_key):
    constellation = meshcore_feeder["node"].constellation
    feeder_b = create_managed_node(
        meshtastic_node_id=None,
        protocol=Protocol.MESHCORE,
        name="MC Feeder B",
        mc_pubkey="c" * 64,
        constellation=constellation,
    )
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 1, "name": "test", "mc_channel_type": "HASHTAG", "mc_hashtag": "test"}],
    )
    reconcile_mc_channels(
        feeder_b,
        [{"mc_channel_idx": 2, "name": "test", "mc_channel_type": "HASHTAG", "mc_hashtag": "test"}],
    )

    now = timezone.now()
    channel_a = resolve_mc_channel(meshcore_feeder["node"], 1)
    channel_b = resolve_mc_channel(feeder_b, 2)
    assert channel_a.id == channel_b.id

    dedup_key = channel_text_dedup_key(
        constellation_id=constellation.id,
        message_channel_id=channel_a.id,
        text="hello #test",
        sender_timestamp=1780409317,
    )
    packet = MeshCoreTextPacket.objects.create(
        observer=meshcore_feeder["node"],
        payload_type=MeshCorePayloadType.CHANNEL_TEXT,
        event_type="channel_message",
        rx_time=now,
        raw_json={},
        text="hello #test",
        channel=channel_a,
        pkt_hash=dedup_key,
    )
    obs_a = MeshCorePacketObservation.objects.create(
        packet=packet,
        observer=meshcore_feeder["node"],
        channel=channel_a,
        rx_time=now,
    )
    msg = MeshCoreTextMessageService().process_packet(packet, meshcore_feeder["node"], obs_a)
    assert msg is not None

    obs_b = MeshCorePacketObservation.objects.create(
        packet=packet,
        observer=feeder_b,
        channel=channel_b,
        rx_time=now,
    )
    assert MeshCoreTextMessageService().process_packet(packet, feeder_b, obs_b) is None
    assert TextMessage.objects.filter(message_text="hello #test").count() == 1
    assert msg.channel_id == channel_a.id
