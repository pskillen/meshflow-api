"""Tests for stats Celery tasks."""

from datetime import datetime
from unittest.mock import patch

from django.utils import timezone

import pytest

from packets.models import DeviceMetricsPacket, PacketObservation
from stats.models import StatsSnapshot
from stats.tasks import _collect_packet_volume, backfill_stats_snapshots


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
    assert "by_type" in hour_12.value


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


@pytest.mark.django_db
def test_packet_volume_includes_by_type(create_managed_node):
    """packet_volume snapshots include by_type breakdown."""
    from packets.models import MessagePacket, PositionPacket
    from stats.tasks import _collect_packet_volume

    hour = timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0))

    MessagePacket.objects.create(
        packet_id=1,
        from_int=111111111,
        first_reported_time=hour,
        message_text="hi",
    )
    PositionPacket.objects.create(
        packet_id=2,
        from_int=222222222,
        first_reported_time=hour + timezone.timedelta(minutes=30),
        latitude=55.0,
        longitude=-3.0,
    )

    c, s = _collect_packet_volume(hour, run_id=None)
    assert c == 1
    assert s == 0

    snap = StatsSnapshot.objects.get(stat_type="packet_volume", recorded_at=hour)
    assert snap.value["count"] == 2
    assert snap.value["by_type"]["text_message"] == 1
    assert snap.value["by_type"]["position"] == 1


@pytest.mark.django_db
def test_packet_volume_excludes_self_only_device_metrics(create_managed_node):
    """packet_volume excludes device metrics that were only observed by the sender."""
    managed = create_managed_node(node_id=111111111)
    channel = managed.channel_0

    hour = timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0))

    # Device metrics from managed's node, observed only by managed (self-ingested)
    dm_self = DeviceMetricsPacket.objects.create(
        packet_id=1,
        from_int=111111111,
        from_str="!069f6b67",
        to_int=4294967295,
        to_str="^all",
        port_num="TELEMETRY_APP",
        first_reported_time=hour,
        reading_time=hour,
        battery_level=95.0,
    )
    PacketObservation.objects.create(
        packet=dm_self,
        observer=managed,
        channel=channel,
        rx_time=hour,
        hop_limit=3,
        hop_start=3,
        rx_rssi=-60.0,
        rx_snr=10.0,
        upload_time=timezone.now(),
        relay_node=None,
    )

    c, s = _collect_packet_volume(hour, run_id=None)
    assert c == 1
    assert s == 0

    snap = StatsSnapshot.objects.get(stat_type="packet_volume", recorded_at=hour)
    # Self-only device metrics should be excluded
    assert snap.value["count"] == 0
    assert snap.value["by_type"]["device_metrics"] == 0


@pytest.mark.django_db
def test_packet_volume_includes_device_metrics_with_other_observer(create_managed_node):
    """packet_volume includes device metrics when observed by a non-sender."""
    managed_b = create_managed_node(node_id=222222222)
    channel_b = managed_b.channel_0

    hour = timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0))

    # Device metrics from node A, observed by node B (mesh traffic)
    dm = DeviceMetricsPacket.objects.create(
        packet_id=1,
        from_int=111111111,
        from_str="!069f6b67",
        to_int=4294967295,
        to_str="^all",
        port_num="TELEMETRY_APP",
        first_reported_time=hour,
        reading_time=hour,
        battery_level=95.0,
    )
    PacketObservation.objects.create(
        packet=dm,
        observer=managed_b,
        channel=channel_b,
        rx_time=hour,
        hop_limit=3,
        hop_start=3,
        rx_rssi=-60.0,
        rx_snr=10.0,
        upload_time=timezone.now(),
        relay_node=None,
    )

    c, s = _collect_packet_volume(hour, run_id=None)
    assert c == 1
    assert s == 0

    snap = StatsSnapshot.objects.get(stat_type="packet_volume", recorded_at=hour)
    assert snap.value["count"] == 1
    assert snap.value["by_type"]["device_metrics"] == 1
