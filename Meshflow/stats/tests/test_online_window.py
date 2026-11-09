"""Online snapshots count nodes heard in [recorded_at - 2h, recorded_at] (api#501)."""

from datetime import datetime, timedelta

from django.core.management import call_command
from django.utils import timezone

import pytest

from meshcore_packets.models import MeshCorePacketObservation, MeshCorePayloadType, MeshCoreRawPacket
from packets.models import MtRawPacket, PacketObservation
from stats.models import StatsSnapshot
from stats.tasks import (
    _collect_mc_online_nodes,
    _collect_online_nodes,
    backfill_stats_snapshots,
    rewrite_online_node_snapshots,
)

HOUR = timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0))
INSIDE = HOUR - timedelta(minutes=30)
AFTER = HOUR + timedelta(minutes=30)
BEFORE = HOUR - timedelta(hours=3)

IN_ONLY, AFTER_ONLY, IN_AND_AFTER, OLD_ONLY = 1001, 1002, 1003, 1004


def _mt_heard(managed, packet_id, sender, when, *, replayed=False):
    packet = MtRawPacket.objects.create(packet_id=packet_id, from_int=sender, first_reported_time=when)
    PacketObservation.objects.create(
        packet=packet, observer=managed, channel=managed.meshtastic_channel_0, rx_time=when, replayed=replayed
    )
    return packet


def _snap(stat_type, constellation=None):
    return StatsSnapshot.objects.get(stat_type=stat_type, recorded_at=HOUR, constellation=constellation)


@pytest.fixture
def mt_world(create_managed_node, create_observed_node):
    managed = create_managed_node(meshtastic_node_id=111111111)
    pid = iter(range(1, 100))
    for sender, times in {
        IN_ONLY: [INSIDE],
        AFTER_ONLY: [AFTER],
        IN_AND_AFTER: [INSIDE, AFTER],
        OLD_ONLY: [BEFORE],
    }.items():
        node = create_observed_node(meshtastic_node_id=sender)
        for when in times:
            _mt_heard(managed, next(pid), sender, when)
        # last_heard is monotonic: it ends at the latest packet, as in production
        node.last_heard = max(times)
        node.save()
    return managed


@pytest.mark.django_db
def test_mt_global_counts_window_only_and_keeps_nodes_heard_again_after(mt_world):
    _collect_online_nodes(HOUR, run_id=None)

    # IN_ONLY and IN_AND_AFTER. Not AFTER_ONLY (heard after recorded_at) nor OLD_ONLY (older than 2h).
    assert _snap("online_nodes").value["count"] == 2
    assert _snap("online_nodes").value["window_hours"] == 2


@pytest.mark.django_db
def test_mt_constellation_row_is_bounded_too(mt_world):
    _collect_online_nodes(HOUR, run_id=None)

    assert _snap("online_nodes", mt_world.constellation).value["count"] == 2


@pytest.mark.django_db
def test_mt_window_edges_are_inclusive(create_managed_node):
    managed = create_managed_node(meshtastic_node_id=111111111)
    _mt_heard(managed, 1, IN_ONLY, HOUR - timedelta(hours=2))
    _mt_heard(managed, 2, AFTER_ONLY, HOUR)
    _mt_heard(managed, 3, OLD_ONLY, HOUR - timedelta(hours=2, seconds=1))

    _collect_online_nodes(HOUR, run_id=None)

    assert _snap("online_nodes").value["count"] == 2


@pytest.mark.django_db
def test_mt_replay_only_sender_is_not_counted(create_managed_node):
    managed = create_managed_node(meshtastic_node_id=111111111)
    _mt_heard(managed, 1, IN_ONLY, INSIDE)
    _mt_heard(managed, 2, AFTER_ONLY, INSIDE, replayed=True)

    _collect_online_nodes(HOUR, run_id=None)

    assert _snap("online_nodes").value["count"] == 1
    assert _snap("online_nodes", managed.constellation).value["count"] == 1


@pytest.mark.django_db
def test_mt_counts_mqtt_heard_nodes(create_managed_node):
    """Online means heard by any transport, so a node only heard over MQTT counts."""
    managed = create_managed_node(meshtastic_node_id=111111111)
    packet = MtRawPacket.objects.create(packet_id=1, from_int=IN_ONLY, first_reported_time=INSIDE)
    PacketObservation.objects.create(
        packet=packet,
        observer=managed,
        channel=managed.meshtastic_channel_0,
        rx_time=INSIDE,
        via_mqtt=True,
    )

    _collect_online_nodes(HOUR, run_id=None)

    assert _snap("online_nodes").value["count"] == 1


def _mc_heard(observer, when, *, pubkey=None, prefix=None):
    packet = MeshCoreRawPacket.objects.create(
        observer=observer,
        payload_type=MeshCorePayloadType.ADVERT,
        event_type="advertisement",
        from_pubkey=pubkey,
        from_pubkey_prefix=prefix,
        rx_time=when,
        first_reported_time=when,
        raw_json={},
    )
    MeshCorePacketObservation.objects.create(packet=packet, observer=observer, rx_time=when)
    return packet


@pytest.fixture
def mc_world(meshcore_feeder):
    observer = meshcore_feeder["node"]
    _mc_heard(observer, INSIDE, pubkey="a" * 64)  # in window only
    _mc_heard(observer, AFTER, pubkey="b" * 64)  # after only
    _mc_heard(observer, INSIDE, pubkey="c" * 64)  # in window and again after
    _mc_heard(observer, AFTER, pubkey="c" * 64)
    _mc_heard(observer, BEFORE, pubkey="d" * 64)  # too old
    return observer


@pytest.mark.django_db
def test_mc_rows_are_bounded_and_keep_nodes_heard_again_after(mc_world):
    _collect_mc_online_nodes(HOUR, run_id=None)

    assert _snap("mc_online_nodes").value["count"] == 2
    assert _snap("mc_online_nodes", mc_world.constellation).value["count"] == 2


@pytest.mark.django_db
def test_mc_prefix_only_sender_counts_once_with_its_full_key(meshcore_feeder):
    observer = meshcore_feeder["node"]
    _mc_heard(observer, INSIDE, pubkey="e" * 64)
    _mc_heard(observer, INSIDE, prefix="e" * 12)  # same node seen by prefix only
    _mc_heard(observer, INSIDE, prefix="f" * 12)  # a node only ever seen by prefix
    _mc_heard(observer, INSIDE)  # no identity at all

    _collect_mc_online_nodes(HOUR, run_id=None)

    assert _snap("mc_online_nodes").value["count"] == 2
    assert _snap("mc_online_nodes", observer.constellation).value["count"] == 2


@pytest.mark.django_db
def test_backfill_and_live_agree(mt_world):
    """The backfill path and the live job use the same window."""
    live = HOUR + timedelta(hours=1, minutes=5)
    _collect_online_nodes(HOUR, run_id=None)
    live_count = _snap("online_nodes").value["count"]
    StatsSnapshot.objects.all().delete()

    from unittest.mock import patch

    with patch("stats.tasks.timezone.now", return_value=live):
        backfill_stats_snapshots.apply(kwargs={"days": 1}).get()

    assert _snap("online_nodes").value["count"] == live_count == 2


# --- rewrite of existing rows


def _stale_row(stat_type, count, *, constellation=None, recorded_at=HOUR):
    return StatsSnapshot.objects.create(
        recorded_at=recorded_at,
        stat_type=stat_type,
        constellation=constellation,
        value={"count": count, "window_hours": 2},
    )


@pytest.mark.django_db
def test_rewrite_corrects_existing_rows_and_is_idempotent(mt_world, mc_world):
    now = HOUR + timedelta(hours=3)
    mt_global = _stale_row("online_nodes", 4)
    mt_const = _stale_row("online_nodes", 4, constellation=mt_world.constellation)
    mc_global = _stale_row("mc_online_nodes", 3)
    mc_const = _stale_row("mc_online_nodes", 3, constellation=mc_world.constellation)

    from unittest.mock import patch

    with patch("stats.tasks.timezone.now", return_value=now):
        first = rewrite_online_node_snapshots.apply(kwargs={"days": 1}).get()
        second = rewrite_online_node_snapshots.apply(kwargs={"days": 1}).get()

    for row in (mt_global, mt_const, mc_global, mc_const):
        row.refresh_from_db()
        assert row.value["count"] == 2
    assert first["rewritten"] == 4
    assert first["earliest_corrected"] == HOUR.isoformat()
    assert second["rewritten"] == 0
    assert second["unchanged"] == 4
    assert second["earliest_corrected"] is None


@pytest.mark.django_db
def test_rewrite_never_inserts_and_leaves_hours_without_raw_packets(mt_world):
    from unittest.mock import patch

    gap_hour = HOUR - timedelta(hours=12)  # no row here, and no packets in its window
    old = _stale_row("online_nodes", 77, recorded_at=HOUR - timedelta(hours=10))  # packets pruned
    now = HOUR + timedelta(hours=3)

    with patch("stats.tasks.timezone.now", return_value=now):
        result = rewrite_online_node_snapshots.apply(kwargs={"days": 1}).get()

    old.refresh_from_db()
    assert old.value["count"] == 77
    assert result["no_raw_packets"] == 1
    assert result["rewritten"] == 0
    assert not StatsSnapshot.objects.filter(recorded_at=gap_hour).exists()
    assert StatsSnapshot.objects.count() == 1


@pytest.mark.django_db
def test_rewrite_dry_run_changes_nothing(mt_world):
    from unittest.mock import patch

    row = _stale_row("online_nodes", 4)

    with patch("stats.tasks.timezone.now", return_value=HOUR + timedelta(hours=3)):
        result = rewrite_online_node_snapshots.apply(kwargs={"days": 1, "dry_run": True}).get()

    row.refresh_from_db()
    assert row.value["count"] == 4
    assert result["rewritten"] == 1


@pytest.mark.django_db
def test_command_rewrite_online_reports_earliest_corrected_hour(mt_world, capsys):
    from io import StringIO
    from unittest.mock import patch

    _stale_row("online_nodes", 4)
    out = StringIO()

    with patch("stats.tasks.timezone.now", return_value=HOUR + timedelta(hours=3)):
        call_command("backfill_stats_snapshots", "--rewrite-online", "--days", "1", stdout=out)

    assert "Earliest corrected hour: " + HOUR.isoformat() in out.getvalue()
