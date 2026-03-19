"""Tests for stats views."""

from datetime import datetime

from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from nodes.models import ObservedNode
from packets.models import DeviceMetricsPacket, MessagePacket, PacketObservation
from stats.models import StatsSnapshot


@pytest.mark.django_db
def test_node_neighbour_stats_returns_empty_for_non_managed_node(create_user):
    """Non-managed nodes should get empty neighbour stats."""
    client = APIClient()
    client.force_authenticate(user=create_user())

    response = client.get(
        reverse("stats:node-neighbour-stats", kwargs={"node_id": 999999999}),
        {"start_date": "2025-01-01", "end_date": "2025-01-02"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["by_source"] == []
    assert response.data["total_packets"] == 0


@pytest.mark.django_db
def test_node_neighbour_stats_uses_from_int_when_relay_node_null(create_managed_node, create_user):
    """When relay_node is null, source should be packet.from_int."""
    user = create_user()
    managed = create_managed_node(owner=user, node_id=111111111)
    channel = managed.channel_0

    packet = MessagePacket.objects.create(
        packet_id=1,
        from_int=222222222,
        from_str="!0d3b6cde",
        to_int=4294967295,
        to_str="^all",
        port_num="TEXT_MESSAGE_APP",
        message_text="Hello",
        first_reported_time=timezone.now(),
    )

    rx_time = timezone.make_aware(datetime(2025, 6, 15, 12, 0, 0))
    PacketObservation.objects.create(
        packet=packet,
        observer=managed,
        channel=channel,
        rx_time=rx_time,
        relay_node=None,
    )

    ObservedNode.objects.get_or_create(
        node_id=222222222,
        defaults={"node_id_str": "!0d3b6cde", "short_name": "SRC", "long_name": "Source Node"},
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(
        reverse("stats:node-neighbour-stats", kwargs={"node_id": managed.node_id}),
        {"start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["by_source"]) == 1
    item = response.data["by_source"][0]
    assert item["source"] == 222222222
    assert item["source_type"] == "full"
    assert item["count"] == 1
    assert len(item["candidates"]) == 1
    assert item["candidates"][0]["node_id"] == 222222222
    assert response.data["total_packets"] == 1


@pytest.mark.django_db
def test_node_neighbour_stats_uses_relay_node_when_set(create_managed_node, create_user):
    """When relay_node is set, source should be relay_node (last hop)."""
    user = create_user()
    managed = create_managed_node(owner=user, node_id=111111111)
    channel = managed.channel_0

    packet = MessagePacket.objects.create(
        packet_id=2,
        from_int=333333333,
        from_str="!13dae5cd",
        to_int=4294967295,
        to_str="^all",
        port_num="TEXT_MESSAGE_APP",
        message_text="Relayed",
        first_reported_time=timezone.now(),
    )

    rx_time = timezone.make_aware(datetime(2025, 6, 15, 12, 0, 0))
    PacketObservation.objects.create(
        packet=packet,
        observer=managed,
        channel=channel,
        rx_time=rx_time,
        relay_node=444444444,
    )

    ObservedNode.objects.get_or_create(
        node_id=444444444,
        defaults={"node_id_str": "!1a7a8b90", "short_name": "RLY", "long_name": "Relay Node"},
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(
        reverse("stats:node-neighbour-stats", kwargs={"node_id": managed.node_id}),
        {"start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["by_source"]) == 1
    item = response.data["by_source"][0]
    assert item["source"] == 444444444
    assert item["source_type"] == "full"
    assert item["count"] == 1
    assert len(item["candidates"]) == 1
    assert item["candidates"][0]["node_id"] == 444444444
    assert response.data["total_packets"] == 1


@pytest.mark.django_db
def test_node_neighbour_stats_uses_from_int_when_relay_node_zero(create_managed_node, create_user):
    """When relay_node is 0, source should fall back to packet.from_int."""
    user = create_user()
    managed = create_managed_node(owner=user, node_id=555555555)
    channel = managed.channel_0

    packet = MessagePacket.objects.create(
        packet_id=3,
        from_int=666666666,
        from_str="!27b8d2de",
        to_int=4294967295,
        to_str="^all",
        port_num="TEXT_MESSAGE_APP",
        message_text="Direct",
        first_reported_time=timezone.now(),
    )

    rx_time = timezone.make_aware(datetime(2025, 6, 15, 12, 0, 0))
    PacketObservation.objects.create(
        packet=packet,
        observer=managed,
        channel=channel,
        rx_time=rx_time,
        relay_node=0,
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(
        reverse("stats:node-neighbour-stats", kwargs={"node_id": managed.node_id}),
        {"start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["by_source"]) == 1
    item = response.data["by_source"][0]
    assert item["source"] == 666666666
    assert item["source_type"] == "full"
    assert response.data["total_packets"] == 1


@pytest.mark.django_db
def test_node_neighbour_stats_aggregates_multiple_sources(create_managed_node, create_user):
    """Multiple packets from different sources should be aggregated correctly."""
    user = create_user()
    managed = create_managed_node(owner=user, node_id=777777777)
    channel = managed.channel_0

    rx_time = timezone.make_aware(datetime(2025, 6, 15, 12, 0, 0))
    for i, (from_id, relay_id) in enumerate([(100, None), (100, None), (200, 300)]):
        packet = MessagePacket.objects.create(
            packet_id=100 + i,
            from_int=from_id,
            from_str=f"!{from_id:08x}",
            to_int=4294967295,
            to_str="^all",
            port_num="TEXT_MESSAGE_APP",
            message_text=f"Msg {i}",
            first_reported_time=rx_time,
        )
        PacketObservation.objects.create(
            packet=packet,
            observer=managed,
            channel=channel,
            rx_time=rx_time,
            relay_node=relay_id,
        )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(
        reverse("stats:node-neighbour-stats", kwargs={"node_id": managed.node_id}),
        {"start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["total_packets"] == 3
    by_source = {s["source"]: s["count"] for s in response.data["by_source"]}
    assert by_source[100] == 2
    assert by_source[300] == 1


@pytest.mark.django_db
def test_node_neighbour_stats_lsb_returns_candidates(create_managed_node, create_user):
    """When relay_node is LSB (<=255), source_type is lsb and candidates list all matching nodes."""
    user = create_user()
    managed = create_managed_node(owner=user, node_id=888888888)
    channel = managed.channel_0

    packet = MessagePacket.objects.create(
        packet_id=4,
        from_int=333333333,
        from_str="!13dae5cd",
        to_int=4294967295,
        to_str="^all",
        port_num="TEXT_MESSAGE_APP",
        message_text="Relayed",
        first_reported_time=timezone.now(),
    )

    rx_time = timezone.make_aware(datetime(2025, 6, 15, 12, 0, 0))
    PacketObservation.objects.create(
        packet=packet,
        observer=managed,
        channel=channel,
        rx_time=rx_time,
        relay_node=24,
    )

    ObservedNode.objects.get_or_create(
        node_id=1129933592,
        defaults={"node_id_str": "!43596b18", "short_name": "NodeA", "long_name": "Node A"},
    )
    ObservedNode.objects.get_or_create(
        node_id=3456789016,
        defaults={"node_id_str": "!ce0e3418", "short_name": "NodeB", "long_name": "Node B"},
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(
        reverse("stats:node-neighbour-stats", kwargs={"node_id": managed.node_id}),
        {"start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["by_source"]) == 1
    item = response.data["by_source"][0]
    assert item["source"] == 24
    assert item["source_type"] == "lsb"
    assert item["count"] == 1
    assert len(item["candidates"]) == 2
    candidate_ids = {c["node_id"] for c in item["candidates"]}
    assert 1129933592 in candidate_ids
    assert 3456789016 in candidate_ids


@pytest.mark.django_db
def test_node_neighbour_stats_excludes_self_packets(create_managed_node, create_user):
    """Packets where the source is the node itself should be excluded."""
    user = create_user()
    managed = create_managed_node(owner=user, node_id=555555555)
    channel = managed.channel_0

    rx_time = timezone.make_aware(datetime(2025, 6, 15, 12, 0, 0))

    # Packet from another node
    packet_other = MessagePacket.objects.create(
        packet_id=1,
        from_int=111111111,
        from_str="!069f6b67",
        to_int=4294967295,
        to_str="^all",
        port_num="TEXT_MESSAGE_APP",
        message_text="From other",
        first_reported_time=rx_time,
    )
    PacketObservation.objects.create(
        packet=packet_other,
        observer=managed,
        channel=channel,
        rx_time=rx_time,
        relay_node=None,
    )

    # Packet from self (direct, relay_node null)
    packet_self = MessagePacket.objects.create(
        packet_id=2,
        from_int=555555555,
        from_str="!211d91a7",
        to_int=4294967295,
        to_str="^all",
        port_num="TEXT_MESSAGE_APP",
        message_text="From self",
        first_reported_time=rx_time,
    )
    PacketObservation.objects.create(
        packet=packet_self,
        observer=managed,
        channel=channel,
        rx_time=rx_time,
        relay_node=None,
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(
        reverse("stats:node-neighbour-stats", kwargs={"node_id": managed.node_id}),
        {"start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["total_packets"] == 1
    assert len(response.data["by_source"]) == 1
    assert response.data["by_source"][0]["source"] == 111111111


@pytest.mark.django_db
def test_node_received_stats_excludes_self_device_metrics(create_managed_node, create_user):
    """node_received_stats excludes observations of device metrics from self."""
    user = create_user()
    managed = create_managed_node(owner=user, node_id=111111111)
    channel = managed.channel_0

    rx_time = timezone.make_aware(datetime(2025, 6, 15, 12, 0, 0))

    # Self device metrics: from_int == managed.node_id, observed by managed
    dm_self = DeviceMetricsPacket.objects.create(
        packet_id=1,
        from_int=111111111,
        from_str="!069f6b67",
        to_int=4294967295,
        to_str="^all",
        port_num="TELEMETRY_APP",
        first_reported_time=rx_time,
        reading_time=rx_time,
        battery_level=95.0,
    )
    PacketObservation.objects.create(
        packet=dm_self,
        observer=managed,
        channel=channel,
        rx_time=rx_time,
        hop_limit=3,
        hop_start=3,
        rx_rssi=-60.0,
        rx_snr=10.0,
        upload_time=timezone.now(),
        relay_node=None,
    )

    # Message from another node (should be included)
    msg = MessagePacket.objects.create(
        packet_id=2,
        from_int=222222222,
        from_str="!0d3b6cde",
        to_int=4294967295,
        to_str="^all",
        port_num="TEXT_MESSAGE_APP",
        message_text="Hello",
        first_reported_time=rx_time,
    )
    PacketObservation.objects.create(
        packet=msg,
        observer=managed,
        channel=channel,
        rx_time=rx_time,
        relay_node=None,
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(
        reverse("stats:node-received-stats", kwargs={"node_id": managed.node_id}),
        {"start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["intervals"]) == 1
    interval = response.data["intervals"][0]
    packet_types = {p["packet_type"]: p["count"] for p in interval["packet_types"]}
    assert packet_types["device_metrics"] == 0
    assert packet_types["text_message"] == 1


@pytest.mark.django_db
def test_node_packet_stats_excludes_self_only_device_metrics(create_managed_node, create_observed_node, create_user):
    """node_packet_stats excludes device metrics that were only self-observed for the node."""
    user = create_user()
    managed = create_managed_node(owner=user, node_id=111111111)
    channel = managed.channel_0

    # ObservedNode for the node (required by node_packet_stats)
    create_observed_node(node_id=111111111)

    rx_time = timezone.make_aware(datetime(2025, 6, 15, 12, 0, 0))

    # Device metrics from node 111111111, observed only by itself (self-ingested)
    dm_self = DeviceMetricsPacket.objects.create(
        packet_id=1,
        from_int=111111111,
        from_str="!069f6b67",
        to_int=4294967295,
        to_str="^all",
        port_num="TELEMETRY_APP",
        first_reported_time=rx_time,
        reading_time=rx_time,
        battery_level=95.0,
    )
    PacketObservation.objects.create(
        packet=dm_self,
        observer=managed,
        channel=channel,
        rx_time=rx_time,
        hop_limit=3,
        hop_start=3,
        rx_rssi=-60.0,
        rx_snr=10.0,
        upload_time=timezone.now(),
        relay_node=None,
    )

    # Message from same node (should be included)
    msg = MessagePacket.objects.create(
        packet_id=2,
        from_int=111111111,
        from_str="!069f6b67",
        to_int=4294967295,
        to_str="^all",
        port_num="TEXT_MESSAGE_APP",
        message_text="Hello",
        first_reported_time=rx_time,
    )
    PacketObservation.objects.create(
        packet=msg,
        observer=managed,
        channel=channel,
        rx_time=rx_time,
        relay_node=None,
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(
        reverse("stats:node-packet-stats", kwargs={"node_id": 111111111}),
        {"start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["intervals"]) == 1
    interval = response.data["intervals"][0]
    packet_types = {p["packet_type"]: p["count"] for p in interval["packet_types"]}
    assert packet_types["device_metrics"] == 0
    assert packet_types["text_message"] == 1


@pytest.mark.django_db
def test_stats_snapshots_list_requires_auth():
    """Stats snapshots endpoint requires authentication."""
    client = APIClient()
    response = client.get(reverse("stats:stats-snapshots"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_stats_snapshots_list_returns_paginated_results(create_user):
    """Stats snapshots list returns paginated results with filters."""
    user = create_user()
    client = APIClient()
    client.force_authenticate(user=user)

    now = timezone.now()
    StatsSnapshot.objects.create(
        recorded_at=now,
        stat_type="online_nodes",
        constellation=None,
        value={"count": 42, "window_hours": 2},
        run_id=None,
    )

    response = client.get(
        reverse("stats:stats-snapshots"),
        {"stat_type": "online_nodes"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "results" in response.data
    assert len(response.data["results"]) >= 1
    item = response.data["results"][0]
    assert item["stat_type"] == "online_nodes"
    assert item["constellation_id"] is None
    assert item["value"]["count"] == 42
