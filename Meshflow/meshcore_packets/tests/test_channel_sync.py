"""Tests for MC channel sync and resolve_mc_channel."""

from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol
from constellations.models import MeshCoreChannelType, MessageChannel
from meshcore_packets.services.channel import resolve_mc_channel
from meshcore_packets.services.channel_sync import reconcile_mc_channels
from meshcore_packets.tests.conftest import FEEDER_MC_PUBKEY_PREFIX, feeder_url


@pytest.fixture
def sync_client(meshcore_feeder):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=meshcore_feeder["api_key"].key)
    return client


@pytest.mark.django_db
def test_reconcile_mc_channels_creates_and_links(meshcore_feeder):
    node = meshcore_feeder["node"]
    channels = reconcile_mc_channels(
        node,
        [
            {
                "mc_channel_idx": 0,
                "name": "Public",
                "mc_channel_type": "PUBLIC",
            },
            {
                "mc_channel_idx": 1,
                "name": "galloway",
                "mc_channel_type": "HASHTAG",
            },
        ],
    )
    assert len(channels) == 2
    node.refresh_from_db()
    assert node.mc_channels.count() == 2
    assert node.mc_channels_synced_at is not None
    ch0 = MessageChannel.objects.get(
        constellation=node.constellation,
        protocol=Protocol.MESHCORE,
        name="Public",
        mc_channel_type=MeshCoreChannelType.PUBLIC,
    )
    assert node.mc_channel_links.filter(mc_channel_idx=0, message_channel=ch0).exists()


@pytest.mark.django_db
def test_reconcile_updates_name_on_resync(meshcore_feeder):
    node = meshcore_feeder["node"]
    reconcile_mc_channels(
        node,
        [{"mc_channel_idx": 0, "name": "Old", "mc_channel_type": "PUBLIC"}],
    )
    reconcile_mc_channels(
        node,
        [{"mc_channel_idx": 0, "name": "Renamed", "mc_channel_type": "PUBLIC"}],
    )
    ch = MessageChannel.objects.get(
        constellation=node.constellation,
        protocol=Protocol.MESHCORE,
        name="Renamed",
        mc_channel_type=MeshCoreChannelType.PUBLIC,
    )
    assert ch.name == "Renamed"


@pytest.mark.django_db
def test_mc_channel_sync_endpoint(sync_client, meshcore_feeder):
    url = feeder_url("meshcore-feeder-mc-channel-sync", FEEDER_MC_PUBKEY_PREFIX)
    response = sync_client.post(
        url,
        {
            "channels": [
                {
                    "mc_channel_idx": 0,
                    "name": "Public",
                    "mc_channel_type": "PUBLIC",
                }
            ],
            "synced_at": timezone.now().isoformat(),
        },
        format="json",
    )
    assert response.status_code == 200
    assert len(response.data["mc_channels"]) == 1
    meshcore_feeder["node"].refresh_from_db()
    assert meshcore_feeder["node"].mc_channels.count() == 1


@pytest.mark.django_db
def test_resolve_mc_channel_prefers_m2m(meshcore_feeder):
    node = meshcore_feeder["node"]
    reconcile_mc_channels(
        node,
        [{"mc_channel_idx": 2, "name": "Synced", "mc_channel_type": "PUBLIC"}],
    )
    ch = resolve_mc_channel(node, 2)
    assert ch.name == "Synced"
    assert ch in node.mc_channels.all()
    assert node.mc_channel_links.filter(mc_channel_idx=2, message_channel=ch).exists()
