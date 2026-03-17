"""Tests for stats Celery tasks."""

from datetime import datetime
from unittest.mock import patch

from django.utils import timezone

import pytest

from packets.models import PacketObservation
from stats.models import StatsSnapshot
from stats.tasks import backfill_stats_snapshots


@pytest.mark.django_db
def test_backfill_stats_snapshots_creates_online_nodes_and_packet_volume(
    create_managed_node,
    create_observed_node,
    create_raw_packet,
    create_packet_observation,
):
    """Backfill creates online_nodes and packet_volume snapshots for each hour."""
    managed = create_managed_node(node_id=111111111)
    channel = managed.channel_0

    # ObservedNode with last_heard in the 2h window before hour 12:00
    observed = create_observed_node(node_id=222222222)
    observed.last_heard = timezone.make_aware(datetime(2025, 3, 15, 11, 30, 0))
    observed.save()

    # RawPacket in hour 12:00
    packet = create_raw_packet(packet_id=1)
    packet.first_reported_time = timezone.make_aware(datetime(2025, 3, 15, 12, 15, 0))
    packet.save()

    PacketObservation.objects.create(
        packet=packet,
        observer=managed,
        channel=channel,
        rx_time=timezone.make_aware(datetime(2025, 3, 15, 12, 15, 0)),
        hop_limit=3,
        hop_start=3,
        rx_rssi=-60.0,
        rx_snr=10.0,
        upload_time=timezone.now(),
        relay_node=None,
    )

    # Mock now to 2025-03-15 16:00 so we backfill 24 hours (days=1)
    end_hour = timezone.make_aware(datetime(2025, 3, 15, 16, 0, 0))

    with patch("stats.tasks.timezone.now", return_value=end_hour):
        result = backfill_stats_snapshots.apply(kwargs={"days": 1})
    data = result.get()

    # 24 hours × (1 global online + 1 constellation online + 1 packet_volume) = 72
    assert data["created"] >= 72
    assert data["skipped"] == 0
    assert data["days"] == 1

    # Verify online_nodes (global)
    online = StatsSnapshot.objects.filter(stat_type="online_nodes", constellation__isnull=True)
    assert online.count() == 24
    assert online.filter(recorded_at=timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0))).exists()

    # Verify packet_volume: hour 12:00 should have our 1 packet
    pv = StatsSnapshot.objects.filter(stat_type="packet_volume")
    assert pv.count() == 24
    hour_12 = pv.get(recorded_at=timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0)))
    assert hour_12.value["count"] == 1


@pytest.mark.django_db
def test_backfill_stats_snapshots_idempotent(
    create_managed_node,
    create_observed_node,
    create_raw_packet,
    create_packet_observation,
):
    """Backfill skips hours that already have snapshots (idempotent)."""
    managed = create_managed_node(node_id=111111111)
    channel = managed.channel_0

    packet = create_raw_packet(packet_id=1)
    packet.first_reported_time = timezone.make_aware(datetime(2025, 3, 15, 12, 15, 0))
    packet.save()

    PacketObservation.objects.create(
        packet=packet,
        observer=managed,
        channel=channel,
        rx_time=timezone.make_aware(datetime(2025, 3, 15, 12, 15, 0)),
        hop_limit=3,
        hop_start=3,
        rx_rssi=-60.0,
        rx_snr=10.0,
        upload_time=timezone.now(),
        relay_node=None,
    )

    end_hour = timezone.make_aware(datetime(2025, 3, 15, 16, 0, 0))

    with patch("stats.tasks.timezone.now", return_value=end_hour):
        result1 = backfill_stats_snapshots.apply(kwargs={"days": 1})
    data1 = result1.get()
    created_first = data1["created"]

    # Second run: should skip all
    with patch("stats.tasks.timezone.now", return_value=end_hour):
        result2 = backfill_stats_snapshots.apply(kwargs={"days": 1})
    data2 = result2.get()

    assert data2["created"] == 0
    assert data2["skipped"] == created_first
