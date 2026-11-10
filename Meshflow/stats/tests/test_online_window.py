"""Online snapshots count nodes heard in the 2h window centred on recorded_at: [H - 1h, H + 1h]."""

from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

import pytest

from common.protocol import Protocol
from meshcore_packets.models import MeshCorePacketObservation, MeshCorePayloadType, MeshCoreRawPacket
from packets.models import MtRawPacket, PacketObservation
from stats.models import StatsSnapshot
from stats.tasks import (
    _collect_mc_online_nodes,
    _collect_online_nodes,
    backfill_stats_snapshots,
    collect_stats_snapshots,
    rewrite_online_node_snapshots,
)

HOUR = timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0))
BEFORE_H = HOUR - timedelta(minutes=30)  # in the window, before the plotted hour
FINISHED_HOUR = HOUR + timedelta(minutes=30)  # in the window, in the hour the point just finished
LATE = HOUR + timedelta(minutes=90)  # after the window
EARLY = HOUR - timedelta(minutes=90)  # before the window
ANCIENT = HOUR - timedelta(hours=3)  # before the window; raw packets exist back this far

IN_BEFORE, IN_FINISHED, LATE_ONLY, IN_AND_LATE, EARLY_ONLY = 1001, 1002, 1003, 1004, 1005


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
        IN_BEFORE: [BEFORE_H],
        IN_FINISHED: [FINISHED_HOUR],
        LATE_ONLY: [LATE],
        IN_AND_LATE: [BEFORE_H, LATE],
        EARLY_ONLY: [EARLY],
    }.items():
        node = create_observed_node(meshtastic_node_id=sender)
        for when in times:
            _mt_heard(managed, next(pid), sender, when)
        # last_heard is monotonic: it ends at the latest packet, as in production
        node.last_heard = max(times)
        node.save()
    _mt_heard(managed, next(pid), 1099, ANCIENT)
    return managed


@pytest.mark.django_db
def test_mt_global_counts_window_and_keeps_nodes_heard_again_after(mt_world):
    _collect_online_nodes(HOUR, run_id=None)

    # IN_BEFORE, IN_FINISHED (the hour just finished) and IN_AND_LATE. Not LATE_ONLY nor EARLY_ONLY/ANCIENT.
    assert _snap("online_nodes").value["count"] == 3
    assert _snap("online_nodes").value["window_hours"] == 2


@pytest.mark.django_db
def test_mt_constellation_row_is_bounded_too(mt_world):
    _collect_online_nodes(HOUR, run_id=None)

    assert _snap("online_nodes", mt_world.constellation).value["count"] == 3


@pytest.mark.django_db
def test_mt_window_edges_are_inclusive(create_managed_node):
    managed = create_managed_node(meshtastic_node_id=111111111)
    _mt_heard(managed, 1, IN_BEFORE, HOUR - timedelta(hours=1))
    _mt_heard(managed, 2, IN_FINISHED, HOUR + timedelta(hours=1))
    _mt_heard(managed, 3, EARLY_ONLY, HOUR - timedelta(hours=1, seconds=1))
    _mt_heard(managed, 4, LATE_ONLY, HOUR + timedelta(hours=1, seconds=1))

    _collect_online_nodes(HOUR, run_id=None)

    assert _snap("online_nodes").value["count"] == 2


@pytest.mark.django_db
def test_mt_replay_only_sender_is_not_counted(create_managed_node):
    managed = create_managed_node(meshtastic_node_id=111111111)
    _mt_heard(managed, 1, IN_BEFORE, BEFORE_H)
    _mt_heard(managed, 2, IN_FINISHED, BEFORE_H, replayed=True)

    _collect_online_nodes(HOUR, run_id=None)

    assert _snap("online_nodes").value["count"] == 1
    assert _snap("online_nodes", managed.constellation).value["count"] == 1


@pytest.mark.django_db
def test_mt_packet_with_replayed_and_real_observations_is_counted(create_managed_node):
    """A packet is dropped only when every observation is a replay; one real hearing is enough."""
    managed = create_managed_node(meshtastic_node_id=111111111)
    other = create_managed_node(meshtastic_node_id=222222222)
    packet = MtRawPacket.objects.create(packet_id=1, from_int=IN_BEFORE, first_reported_time=BEFORE_H)
    PacketObservation.objects.create(
        packet=packet, observer=managed, channel=managed.meshtastic_channel_0, rx_time=BEFORE_H, replayed=True
    )
    PacketObservation.objects.create(
        packet=packet, observer=other, channel=other.meshtastic_channel_0, rx_time=BEFORE_H, replayed=False
    )

    _collect_online_nodes(HOUR, run_id=None)

    assert _snap("online_nodes").value["count"] == 1
    assert _snap("online_nodes", other.constellation).value["count"] == 1
    assert _snap("online_nodes", managed.constellation).value["count"] == 0  # its only hearing was a replay


@pytest.mark.django_db
def test_mt_counts_mqtt_heard_nodes(create_managed_node):
    """Online means heard by any transport, so a node only heard over MQTT counts."""
    managed = create_managed_node(meshtastic_node_id=111111111)
    packet = MtRawPacket.objects.create(packet_id=1, from_int=IN_BEFORE, first_reported_time=BEFORE_H)
    PacketObservation.objects.create(
        packet=packet,
        observer=managed,
        channel=managed.meshtastic_channel_0,
        rx_time=BEFORE_H,
        via_mqtt=True,
    )

    _collect_online_nodes(HOUR, run_id=None)

    assert _snap("online_nodes").value["count"] == 1


@pytest.mark.django_db
def test_mt_two_constellations_are_counted_separately(create_managed_node):
    """Each constellation counts what its own feeders heard; the global row counts everyone once."""
    first = create_managed_node(meshtastic_node_id=111111111)
    second = create_managed_node(meshtastic_node_id=222222222)
    assert first.constellation_id != second.constellation_id
    _mt_heard(first, 1, IN_BEFORE, BEFORE_H)
    _mt_heard(first, 2, IN_FINISHED, BEFORE_H)
    _mt_heard(second, 3, IN_FINISHED, BEFORE_H)
    _mt_heard(second, 4, EARLY_ONLY, EARLY)

    _collect_online_nodes(HOUR, run_id=None)

    assert _snap("online_nodes", first.constellation).value["count"] == 2
    assert _snap("online_nodes", second.constellation).value["count"] == 1
    assert _snap("online_nodes").value["count"] == 2


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
    _mc_heard(observer, BEFORE_H, pubkey="a" * 64)  # in window only
    _mc_heard(observer, FINISHED_HOUR, pubkey="b" * 64)  # in the hour just finished
    _mc_heard(observer, LATE, pubkey="c" * 64)  # late only
    _mc_heard(observer, BEFORE_H, pubkey="d" * 64)  # in window and again late
    _mc_heard(observer, LATE, pubkey="d" * 64)
    _mc_heard(observer, ANCIENT, pubkey="e" * 64)  # too old
    return observer


@pytest.mark.django_db
def test_mc_rows_are_bounded_and_keep_nodes_heard_again_after(mc_world):
    _collect_mc_online_nodes(HOUR, run_id=None)

    assert _snap("mc_online_nodes").value["count"] == 3
    assert _snap("mc_online_nodes", mc_world.constellation).value["count"] == 3


@pytest.mark.django_db
def test_mc_prefix_only_sender_counts_once_with_its_full_key(meshcore_feeder):
    observer = meshcore_feeder["node"]
    _mc_heard(observer, BEFORE_H, pubkey="e" * 64)
    _mc_heard(observer, BEFORE_H, prefix="e" * 12)  # same node seen by prefix only
    _mc_heard(observer, BEFORE_H, prefix="f" * 12)  # a node only ever seen by prefix
    _mc_heard(observer, BEFORE_H)  # no identity at all

    _collect_mc_online_nodes(HOUR, run_id=None)

    assert _snap("mc_online_nodes").value["count"] == 2
    assert _snap("mc_online_nodes", observer.constellation).value["count"] == 2


@pytest.mark.django_db
def test_mc_sender_heard_by_two_observers_counts_once_globally(meshcore_feeder, create_managed_node):
    """One advert heard by two feeders in different constellations: once globally, once in each."""
    first = meshcore_feeder["node"]
    second = create_managed_node(
        meshtastic_node_id=None, protocol=Protocol.MESHCORE, name="MC Feeder 2", mc_pubkey="9" * 64
    )
    assert first.constellation_id != second.constellation_id
    _mc_heard(first, BEFORE_H, pubkey="a" * 64)
    _mc_heard(second, BEFORE_H + timedelta(minutes=1), pubkey="a" * 64)

    _collect_mc_online_nodes(HOUR, run_id=None)

    assert _snap("mc_online_nodes").value["count"] == 1
    assert _snap("mc_online_nodes", first.constellation).value["count"] == 1
    assert _snap("mc_online_nodes", second.constellation).value["count"] == 1


@pytest.mark.django_db
def test_live_job_and_backfill_agree(mt_world):
    """The hourly job and the backfill write the same count for the same hour."""
    with patch("stats.tasks.timezone.now", return_value=HOUR + timedelta(hours=1, minutes=5)):
        collect_stats_snapshots.apply().get()
    live_count = _snap("online_nodes").value["count"]
    StatsSnapshot.objects.all().delete()

    with patch("stats.tasks.timezone.now", return_value=HOUR + timedelta(hours=1, minutes=5)):
        backfill_stats_snapshots.apply(kwargs={"days": 1}).get()

    assert _snap("online_nodes").value["count"] == live_count == 3


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
    mt_global = _stale_row("online_nodes", 5)
    mt_const = _stale_row("online_nodes", 5, constellation=mt_world.constellation)
    mc_global = _stale_row("mc_online_nodes", 4)
    mc_const = _stale_row("mc_online_nodes", 4, constellation=mc_world.constellation)

    with patch("stats.tasks.timezone.now", return_value=now):
        first = rewrite_online_node_snapshots.apply(kwargs={"days": 1}).get()
        second = rewrite_online_node_snapshots.apply(kwargs={"days": 1}).get()

    for row in (mt_global, mt_const, mc_global, mc_const):
        row.refresh_from_db()
        assert row.value["count"] == 3
    assert first["rewritten"] == 4
    assert first["earliest_corrected"] == HOUR.isoformat()
    assert second["rewritten"] == 0
    assert second["unchanged"] == 4
    assert second["earliest_corrected"] is None


@pytest.mark.django_db
def test_rewrite_never_inserts_and_leaves_rows_raw_packets_do_not_cover(mt_world):
    gap_hour = HOUR - timedelta(hours=12)  # no row here, and no raw packets that far back
    old = _stale_row("online_nodes", 77, recorded_at=HOUR - timedelta(hours=10))  # packets pruned
    now = HOUR + timedelta(hours=3)

    with patch("stats.tasks.timezone.now", return_value=now):
        result = rewrite_online_node_snapshots.apply(kwargs={"days": 1}).get()

    old.refresh_from_db()
    assert old.value["count"] == 77
    assert result["left_alone"] == 1
    assert result["rewritten"] == 0
    assert not StatsSnapshot.objects.filter(recorded_at=gap_hour).exists()
    assert StatsSnapshot.objects.count() == 1


@pytest.mark.django_db
def test_rewrite_leaves_a_row_whose_window_starts_before_the_oldest_raw_packet(create_managed_node):
    """Raw data that starts partway through a window would undercount it, so the row keeps its value."""
    managed = create_managed_node(meshtastic_node_id=111111111)
    _mt_heard(managed, 1, IN_BEFORE, BEFORE_H)  # oldest raw packet is 30 min into the window [H-1h, H+1h]
    partial = _stale_row("online_nodes", 9)
    covered = _stale_row("online_nodes", 9, recorded_at=HOUR + timedelta(hours=1))  # window starts at H, after it

    with patch("stats.tasks.timezone.now", return_value=HOUR + timedelta(hours=4)):
        result = rewrite_online_node_snapshots.apply(kwargs={"days": 1}).get()

    partial.refresh_from_db()
    covered.refresh_from_db()
    assert partial.value["count"] == 9
    assert covered.value["count"] == 0
    assert result["left_alone"] == 1
    assert result["rewritten"] == 1
    assert result["earliest_covered"] == (HOUR + timedelta(hours=1)).isoformat()


@pytest.mark.django_db
def test_rewrite_dry_run_changes_nothing(mt_world):
    row = _stale_row("online_nodes", 5)

    with patch("stats.tasks.timezone.now", return_value=HOUR + timedelta(hours=3)):
        result = rewrite_online_node_snapshots.apply(kwargs={"days": 1, "dry_run": True}).get()

    row.refresh_from_db()
    assert row.value["count"] == 5
    assert result["rewritten"] == 1


@pytest.mark.django_db
def test_command_rewrite_online_reports_earliest_corrected_hour(mt_world):
    _stale_row("online_nodes", 5)
    out = StringIO()

    with patch("stats.tasks.timezone.now", return_value=HOUR + timedelta(hours=3)):
        call_command("backfill_stats_snapshots", "--rewrite-online", "--days", "1", stdout=out)

    assert "Earliest corrected hour: " + HOUR.isoformat() in out.getvalue()


@pytest.mark.django_db
def test_command_dry_run_without_rewrite_online_is_an_error():
    with pytest.raises(CommandError, match="--dry-run requires --rewrite-online"):
        call_command("backfill_stats_snapshots", "--dry-run", stdout=StringIO())
