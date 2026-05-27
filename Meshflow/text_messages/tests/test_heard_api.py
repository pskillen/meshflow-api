"""Message list heard[] path and position fields."""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.tests.conftest import FEEDER_MC_PUBKEY_PREFIX, feeder_url
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
