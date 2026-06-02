"""Tests for meshcore_packets.services.dedup_key."""

import pytest

from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.services.dedup import SIGNED_BIGINT_MAX, surrogate_pkt_hash
from meshcore_packets.services.dedup_key import (
    channel_text_dedup_key,
    extract_sender_timestamp,
    resolve_ingest_dedup_key,
)


def test_extract_sender_timestamp_from_nested_envelope():
    data = {
        "raw": {
            "protocol": "meshcore",
            "event_type": "channel_message",
            "payload": {"sender_timestamp": 1780409317, "text": "hello"},
        },
    }
    assert extract_sender_timestamp(data) == 1780409317


def test_surrogate_pkt_hash_fits_postgresql_bigint():
    key = surrogate_pkt_hash(event_type="channel_message", raw_payload="x" * 5000)
    assert 0 <= key <= SIGNED_BIGINT_MAX


def test_channel_text_dedup_key_stable_across_feeder_envelopes():
    constellation_id = "11111111-1111-1111-1111-111111111111"
    channel_id = "22222222-2222-2222-2222-222222222222"
    text = "PDY4 Paddy Mobile 4: Ping"
    ts = 1780409317
    key_a = channel_text_dedup_key(
        constellation_id=constellation_id,
        message_channel_id=channel_id,
        text=text,
        sender_timestamp=ts,
    )
    key_b = channel_text_dedup_key(
        constellation_id=constellation_id,
        message_channel_id=channel_id,
        text=text,
        sender_timestamp=ts,
    )
    assert key_a == key_b

    surrogate_a = surrogate_pkt_hash(
        event_type="channel_message",
        raw_payload=str({"rssi": -40, "text": text}),
    )
    surrogate_b = surrogate_pkt_hash(
        event_type="channel_message",
        raw_payload=str({"rssi": -90, "text": text}),
    )
    assert key_a != surrogate_a
    assert key_a != surrogate_b


def test_resolve_ingest_dedup_key_prefers_wire_hash():
    wire = 42424242

    class _Observer:
        constellation_id = None

    key = resolve_ingest_dedup_key(
        validated_data={
            "payload_type": "channel_text",
            "event_type": "channel_message",
            "pkt_hash": wire,
            "text": "ignored for wire",
            "raw": {},
        },
        observer=_Observer(),
        channel=None,
    )
    assert key == wire


@pytest.mark.django_db
def test_resolve_ingest_dedup_key_channel_content(meshcore_feeder):
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    channel = meshcore_feeder["node"].mc_channels.first()
    key = resolve_ingest_dedup_key(
        validated_data={
            "payload_type": "channel_text",
            "event_type": "channel_message",
            "text": "hello mesh",
            "raw": {"payload": {"sender_timestamp": 99}},
        },
        observer=meshcore_feeder["node"],
        channel=channel,
    )
    expected = channel_text_dedup_key(
        constellation_id=meshcore_feeder["node"].constellation_id,
        message_channel_id=channel.id,
        text="hello mesh",
        sender_timestamp=99,
    )
    assert key == expected
