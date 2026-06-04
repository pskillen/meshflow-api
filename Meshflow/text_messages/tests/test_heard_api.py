"""Message list heard[] path and position fields."""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol
from meshcore_packet_path.models import MeshCorePathSegmentResolution, SegmentStatus
from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.tests.conftest import FEEDER_MC_PUBKEY_PREFIX, feeder_url
from nodes.models import NodeLatestStatus, ObservedNode
from text_messages.models import TextMessage


@pytest.fixture
def ingest_client(meshcore_feeder):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=meshcore_feeder["api_key"].key)
    return client


@pytest.mark.django_db
def test_mc_message_heard_includes_path_display(meshcore_feeder, ingest_client):
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    now = timezone.now()
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    ingest_client.post(
        url,
        {
            "event_type": "channel_message",
            "payload_type": "channel_text",
            "channel_idx": 0,
            "pkt_hash": 88010,
            "rx_time": now.timestamp(),
            "text": "heard path ui",
            "path_hashes": ["ab", "cd"],
            "raw": {},
        },
        format="json",
    )
    tm = TextMessage.objects.get(message_text="heard path ui")
    client = APIClient()
    list_url = reverse("textmessage-list")
    response = client.get(list_url, {"channel_id": tm.channel_id})
    assert response.status_code == 200
    row = next(item for item in response.data["results"] if item["id"] == str(tm.id))
    assert row["sender_position"] is None
    assert len(row["heard"]) == 1
    heard = row["heard"][0]
    assert heard["path_hashes"] == ["ab", "cd"]
    assert heard["path_known"] is False
    assert heard["resolved_path"][0]["hash"] == "ab"
    assert heard["resolved_path"][0]["status"] == "unknown"
    assert "observer" in heard
    assert heard["observer"]["node_id_str"].startswith("mc:")


@pytest.mark.django_db
def test_message_list_query_count_bounded(meshcore_feeder, ingest_client):
    """Prefetch observations and bulk path hop cache — no per-message observation query."""
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    now = timezone.now()
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    for idx in range(3):
        ingest_client.post(
            url,
            {
                "event_type": "channel_message",
                "payload_type": "channel_text",
                "channel_idx": 0,
                "pkt_hash": 88020 + idx,
                "rx_time": now.timestamp(),
                "text": f"batch {idx}",
                "path_hashes": [f"{idx}a"],
                "raw": {},
            },
            format="json",
        )

    client = APIClient()
    list_url = reverse("textmessage-list")
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(list_url)
    assert response.status_code == 200
    assert len(response.data["results"]) >= 3
    assert len(ctx) <= 25


@pytest.mark.django_db
def test_mc_message_heard_path_via_rx_log_twin(meshcore_feeder, ingest_client):
    """Tier 1: channel_text without path + raw PATH twin → heard[] shows path_hashes."""
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    now = timezone.now()
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    rx_time = now.timestamp()
    message_text = "tier1 heard twin path"

    ingest_client.post(
        url,
        {
            "event_type": "channel_message",
            "payload_type": "channel_text",
            "channel_idx": 0,
            "rx_time": rx_time,
            "text": message_text,
            "path_hash_size": 2,
            "path_hash_mode": 2,
            "raw": {},
        },
        format="json",
    )
    ingest_client.post(
        url,
        {
            "event_type": "rx_log_data",
            "payload_type": "raw",
            "pkt_hash": 3138934464,
            "rx_time": rx_time,
            "path_hashes": ["ab", "cd"],
            "path_hash_size": 2,
            "raw": {
                "protocol": "meshcore",
                "event_type": "rx_log_data",
                "payload": {"payload_typename": "PATH", "path": "abcd"},
            },
        },
        format="json",
    )

    tm = TextMessage.objects.get(message_text=message_text)
    client = APIClient()
    list_url = reverse("textmessage-list")
    response = client.get(list_url, {"channel_id": tm.channel_id})
    row = next(item for item in response.data["results"] if item["id"] == str(tm.id))
    assert row["heard"][0]["path_hashes"] == ["ab", "cd"]


@pytest.mark.django_db
def test_mc_message_heard_resolved_path_from_segment_table(meshcore_feeder, ingest_client):
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    node = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey="b" * 64,
        mc_pubkey_prefix="b" * 12,
        long_name="Hop Node",
    )
    NodeLatestStatus.objects.create(
        node=node,
        latitude=55.95,
        longitude=-4.25,
    )
    MeshCorePathSegmentResolution.objects.create(
        segment_hash="ab",
        hash_size=2,
        status=SegmentStatus.RESOLVED,
        observed_node=node,
    )
    now = timezone.now()
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    ingest_client.post(
        url,
        {
            "event_type": "channel_message",
            "payload_type": "channel_text",
            "channel_idx": 0,
            "pkt_hash": 88011,
            "rx_time": now.timestamp(),
            "text": "resolved hop map test",
            "path_hashes": ["ab"],
            "raw": {},
        },
        format="json",
    )
    tm = TextMessage.objects.get(message_text="resolved hop map test")
    client = APIClient()
    response = client.get(reverse("textmessage-list"), {"channel_id": tm.channel_id})
    row = next(item for item in response.data["results"] if item["id"] == str(tm.id))
    hop = row["heard"][0]["resolved_path"][0]
    assert hop["status"] == "resolved"
    assert hop["node_id_str"] == node.node_id_str
    assert hop["position"]["latitude"] == 55.95
    assert row["heard"][0]["path_known"] is True


@pytest.mark.django_db
def test_mc_message_heard_ambiguous_hop_candidates(meshcore_feeder, ingest_client):
    reconcile_mc_channels(
        meshcore_feeder["node"],
        [{"mc_channel_idx": 0, "name": "Public", "mc_channel_type": "PUBLIC"}],
    )
    for name, letter in (("Node A", "a"), ("Node B", "b")):
        node = ObservedNode.objects.create(
            protocol=Protocol.MESHCORE,
            mc_pubkey=letter * 64,
            mc_pubkey_prefix=f"{letter * 8}cafe",
            long_name=name,
        )
        NodeLatestStatus.objects.create(node=node, latitude=55.0, longitude=-4.0)
    now = timezone.now()
    url = feeder_url("meshcore-feeder-packet-ingest", FEEDER_MC_PUBKEY_PREFIX)
    ingest_client.post(
        url,
        {
            "event_type": "channel_message",
            "payload_type": "channel_text",
            "channel_idx": 0,
            "pkt_hash": 88012,
            "rx_time": now.timestamp(),
            "text": "ambiguous hop test",
            "path_hashes": ["cafe"],
            "path_hash_size": 2,
            "raw": {},
        },
        format="json",
    )
    tm = TextMessage.objects.get(message_text="ambiguous hop test")
    client = APIClient()
    response = client.get(reverse("textmessage-list"), {"channel_id": tm.channel_id})
    row = next(item for item in response.data["results"] if item["id"] == str(tm.id))
    heard = row["heard"][0]
    assert heard["path_hash_size"] == 2
    hop = heard["resolved_path"][0]
    assert hop["status"] == "ambiguous"
    assert len(hop["candidates"]) == 2
