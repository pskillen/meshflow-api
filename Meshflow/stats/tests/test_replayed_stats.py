"""Stats over observations exclude 2.8 connect-time replays (replayed=True)."""

from datetime import datetime

from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from nodes.models import ObservedNode
from packets.models import MessagePacket, PacketObservation
from stats.models import StatsSnapshot
from stats.tasks import _collect_new_nodes, _collect_online_nodes, _collect_packet_volume

MANAGED = 111111111
LIVE_SENDER = 222222222
REPLAY_SENDER = 333333333
RX = timezone.make_aware(datetime(2025, 6, 15, 12, 0, 0))
RANGE = {"start_date": "2025-01-01", "end_date": "2025-12-31"}


def _observe(packet_id, sender, observer, *, replayed, rx_time=RX):
    packet = MessagePacket.objects.create(
        packet_id=packet_id, from_int=sender, first_reported_time=rx_time, message_text="hi"
    )
    return PacketObservation.objects.create(
        packet=packet,
        observer=observer,
        channel=observer.meshtastic_channel_0,
        rx_time=rx_time,
        replayed=replayed,
    )


@pytest.fixture
def world(create_managed_node, create_user):
    user = create_user()
    managed = create_managed_node(owner=user, meshtastic_node_id=MANAGED)
    for num in (MANAGED, LIVE_SENDER, REPLAY_SENDER):
        ObservedNode.objects.get_or_create(meshtastic_node_id=num, defaults={"short_name": "N", "long_name": "Node"})
    _observe(1, LIVE_SENDER, managed, replayed=False)
    _observe(2, REPLAY_SENDER, managed, replayed=True)
    client = APIClient()
    client.force_authenticate(user=user)
    return {"managed": managed, "client": client}


def _total(response):
    return sum(p["count"] for i in response.data["intervals"] for p in i["packet_types"])


@pytest.mark.django_db
def test_node_packet_stats_counts_only_packets_with_a_live_observation(world):
    url = lambda n: reverse("stats:node-packet-stats", kwargs={"node_id": n})  # noqa: E731

    assert _total(world["client"].get(url(LIVE_SENDER), RANGE)) == 1
    assert _total(world["client"].get(url(REPLAY_SENDER), RANGE)) == 0


@pytest.mark.django_db
def test_node_packet_stats_counts_a_replayed_packet_also_seen_live(world, create_managed_node):
    other = create_managed_node(meshtastic_node_id=444444444)
    replay_only = PacketObservation.objects.get(packet__from_int=REPLAY_SENDER).packet
    PacketObservation.objects.create(
        packet=replay_only, observer=other, channel=other.meshtastic_channel_0, rx_time=RX, replayed=False
    )

    response = world["client"].get(reverse("stats:node-packet-stats", kwargs={"node_id": REPLAY_SENDER}), RANGE)

    assert _total(response) == 1


@pytest.mark.django_db
def test_node_received_stats_counts_only_live_observations(world):
    response = world["client"].get(reverse("stats:node-received-stats", kwargs={"node_id": MANAGED}), RANGE)

    assert response.status_code == 200
    assert _total(response) == 1


@pytest.mark.django_db
def test_node_neighbour_stats_counts_only_live_observations(world):
    response = world["client"].get(reverse("stats:node-neighbour-stats", kwargs={"node_id": MANAGED}), RANGE)

    assert response.status_code == 200
    assert response.data["total_packets"] == 1
    assert [item["source"] for item in response.data["by_source"]] == [LIVE_SENDER]


@pytest.mark.django_db
def test_online_nodes_snapshot_counts_only_live_senders(world):
    hour = timezone.make_aware(datetime(2025, 6, 15, 13, 0, 0))

    _collect_online_nodes(hour, run_id=None)

    snap = StatsSnapshot.objects.get(
        stat_type="online_nodes", constellation=world["managed"].constellation, recorded_at=hour
    )
    assert snap.value["count"] == 1


@pytest.mark.django_db
def test_new_nodes_snapshot_counts_only_live_senders(world):
    _collect_new_nodes(RX, run_id=None)

    snap = StatsSnapshot.objects.get(
        stat_type="new_nodes", constellation=world["managed"].constellation, recorded_at=RX
    )
    assert snap.value["count"] == 1


@pytest.mark.django_db
def test_packet_volume_excludes_replay_only_packets(world):
    _collect_packet_volume(RX, run_id=None)

    snap = StatsSnapshot.objects.get(stat_type="packet_volume", recorded_at=RX)
    assert snap.value["count"] == 1


@pytest.mark.django_db
def test_global_packet_stats_excludes_replay_only_packets(world):
    response = world["client"].get(reverse("stats:global-packet-stats"), RANGE)

    assert response.status_code == 200
    assert response.data["summary"]["total_packets"] == 1
