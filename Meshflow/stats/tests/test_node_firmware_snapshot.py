"""Tests for the daily node_firmware snapshot and its backfill."""

import datetime as dt
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest

from common.protocol import Protocol
from stats.models import StatsSnapshot
from stats.tasks import (
    NODE_FIRMWARE_STAT,
    _node_firmware_value,
    backfill_node_firmware_snapshots,
    collect_stats_snapshots,
)

UTC = dt.timezone.utc
MIDNIGHT = dt.datetime(2025, 6, 10, 0, 0, tzinfo=UTC)
RUN_AT = dt.datetime(2025, 6, 10, 0, 5, tzinfo=UTC)


def _node(create_observed_node, node_id, last_heard, firmware=None, basis=None, **kwargs):
    node = create_observed_node(meshtastic_node_id=node_id, **kwargs)
    node.last_heard = last_heard
    node.inferred_firmware = firmware
    node.inferred_firmware_basis = basis
    node.save()
    return node


def _run_at(when):
    with patch("stats.tasks.timezone.now", return_value=when):
        return collect_stats_snapshots()


def _fw_snapshots():
    return StatsSnapshot.objects.filter(stat_type=NODE_FIRMWARE_STAT)


def test_value_builder_maps_and_seeds():
    value = _node_firmware_value(
        [
            ("2.8", "key_identity", 3),
            ("2.7", "feeder_report", 2),
            (None, None, 4),
            ("2.7", "other_basis", 1),
        ]
    )
    assert value == {
        "count": 10,
        "window_hours": 168,
        "by_type": {"2.8": 3, "2.7": 3, "unknown": 4},
        "by_basis": {"key_identity": 3, "predicted_id": 0, "reported": 2, "none": 4, "other_basis": 1},
    }


@pytest.mark.django_db
def test_written_at_midnight_only_and_idempotent():
    _run_at(dt.datetime(2025, 6, 10, 13, 5, tzinfo=UTC))
    assert _fw_snapshots().count() == 0

    _run_at(RUN_AT)
    _run_at(RUN_AT)
    snaps = list(_fw_snapshots())
    assert len(snaps) == 1
    assert snaps[0].recorded_at == MIDNIGHT
    assert snaps[0].constellation is None


@pytest.mark.django_db
def test_exact_value(create_observed_node):
    heard = MIDNIGHT - dt.timedelta(hours=1)
    _node(create_observed_node, 1001, heard, "2.8", "key_identity")
    _node(create_observed_node, 1002, heard, "2.8", "key_identity")
    _node(create_observed_node, 1003, heard, "2.7", "predicted_id")
    _node(create_observed_node, 1004, heard, "2.7", "feeder_report")
    _node(create_observed_node, 1005, heard)

    _run_at(RUN_AT)

    assert _fw_snapshots().get().value == {
        "count": 5,
        "window_hours": 168,
        "by_type": {"2.8": 2, "2.7": 2, "unknown": 1},
        "by_basis": {"key_identity": 2, "predicted_id": 1, "reported": 1, "none": 1},
    }


@pytest.mark.django_db
def test_empty_value_has_seeded_keys():
    _run_at(RUN_AT)
    assert _fw_snapshots().get().value == {
        "count": 0,
        "window_hours": 168,
        "by_type": {},
        "by_basis": {"key_identity": 0, "predicted_id": 0, "reported": 0, "none": 0},
    }


@pytest.mark.django_db
def test_window_boundary_no_upper_bound_and_meshcore_excluded(create_observed_node):
    edge = MIDNIGHT - dt.timedelta(hours=168)
    _node(create_observed_node, 2001, edge, "2.7", "key_identity")
    _node(create_observed_node, 2002, edge - dt.timedelta(seconds=1), "2.7", "key_identity")
    _node(create_observed_node, 2003, MIDNIGHT + dt.timedelta(minutes=3), "2.8", "key_identity")
    _node(
        create_observed_node,
        2004,
        MIDNIGHT - dt.timedelta(hours=1),
        "2.8",
        "key_identity",
        protocol=Protocol.MESHCORE,
    )

    _run_at(RUN_AT)

    value = _fw_snapshots().get().value
    assert value["count"] == 2
    assert value["by_type"] == {"2.7": 1, "2.8": 1}


@pytest.mark.django_db
def test_new_generation_appears_as_key(create_observed_node):
    _node(create_observed_node, 3001, MIDNIGHT - dt.timedelta(hours=1), "2.9", "key_identity")
    _run_at(RUN_AT)
    assert _fw_snapshots().get().value["by_type"] == {"2.9": 1}


# --- backfill ---


def _packet(create_raw_packet, packet_id, from_int, when):
    packet = create_raw_packet(packet_id=packet_id, from_int=from_int)
    packet.first_reported_time = when
    packet.save()


@pytest.fixture
def backfill_data(create_observed_node, create_raw_packet):
    """Today is 2025-06-10 12:00 UTC; node A heard 06-08, node B and unknown C heard 06-09."""
    _node(create_observed_node, 5001, None, "2.8", "key_identity")
    _node(create_observed_node, 5002, None, "2.7", "feeder_report")
    _packet(create_raw_packet, 1, 5001, dt.datetime(2025, 6, 8, 23, 0, tzinfo=UTC))
    _packet(create_raw_packet, 2, 5001, dt.datetime(2025, 6, 8, 23, 30, tzinfo=UTC))
    _packet(create_raw_packet, 3, 5002, dt.datetime(2025, 6, 9, 1, 0, tzinfo=UTC))
    _packet(create_raw_packet, 4, 5003, dt.datetime(2025, 6, 9, 2, 0, tzinfo=UTC))
    return dt.datetime(2025, 6, 10, 12, 0, tzinfo=UTC)


def _backfill(now, **kwargs):
    with patch("stats.tasks.timezone.now", return_value=now):
        return backfill_node_firmware_snapshots(**kwargs)


@pytest.mark.django_db
def test_backfill_per_day_values(backfill_data):
    result = _backfill(backfill_data, days=3)

    assert result["created"] == 3
    by_day = {s.recorded_at: s.value for s in _fw_snapshots()}
    assert by_day[dt.datetime(2025, 6, 8, tzinfo=UTC)]["count"] == 0
    assert by_day[dt.datetime(2025, 6, 9, tzinfo=UTC)]["by_type"] == {"2.8": 1}
    assert by_day[MIDNIGHT] == {
        "count": 3,
        "window_hours": 168,
        "by_type": {"2.8": 1, "2.7": 1, "unknown": 1},
        "by_basis": {"key_identity": 1, "predicted_id": 0, "reported": 1, "none": 1},
    }


@pytest.mark.django_db
def test_backfill_single_packet_query(backfill_data):
    with CaptureQueriesContext(connection) as ctx:
        _backfill(backfill_data, days=3)
    touching = [q for q in ctx.captured_queries if "packets_mt_raw_packet" in q["sql"]]
    assert len(touching) == 1


@pytest.mark.django_db
def test_backfill_idempotent(backfill_data):
    _backfill(backfill_data, days=3)
    again = _backfill(backfill_data, days=3)
    assert again["created"] == 0
    assert again["skipped"] == 3
    assert _fw_snapshots().count() == 3


@pytest.mark.django_db
def test_backfill_dry_run_writes_nothing(backfill_data):
    dry = _backfill(backfill_data, days=3, dry_run=True)
    assert _fw_snapshots().count() == 0
    real = _backfill(backfill_data, days=3)
    assert (dry["created"], dry["skipped"], dry["scanned"]) == (real["created"], real["skipped"], real["scanned"])


@pytest.mark.django_db
def test_backfill_command_output(backfill_data, capsys):
    from django.core.management import call_command

    with patch("stats.tasks.timezone.now", return_value=backfill_data):
        call_command("backfill_node_firmware_snapshots", "--days", "3", "--dry-run")
    out = capsys.readouterr().out
    assert out.startswith("[dry-run] Scanned 3 day/node rows in ")
    assert "[dry-run] Snapshots: created 3, already present 0" in out
    assert _fw_snapshots().count() == 0


@pytest.mark.django_db
def test_backfill_rejects_non_positive_days(backfill_data):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    assert _backfill(backfill_data, days=0)["created"] == 0
    with pytest.raises(CommandError):
        call_command("backfill_node_firmware_snapshots", "--days", "0")
    assert _fw_snapshots().count() == 0


@pytest.mark.django_db
def test_live_run_skips_midnight_written_by_backfill(backfill_data):
    _backfill(backfill_data, days=1)
    before = list(_fw_snapshots().values_list("id", flat=True))
    assert len(before) == 1

    _run_at(RUN_AT)
    assert list(_fw_snapshots().values_list("id", flat=True)) == before


@pytest.mark.django_db
def test_backfill_seven_day_edge(create_observed_node, create_raw_packet):
    _node(create_observed_node, 6001, None, "2.8", "key_identity")
    _node(create_observed_node, 6002, None, "2.7", "feeder_report")
    # Window for the 06-10 midnight is 06-03..06-09 (UTC days).
    _packet(create_raw_packet, 11, 6001, dt.datetime(2025, 6, 3, 0, 0, tzinfo=UTC))
    _packet(create_raw_packet, 12, 6002, dt.datetime(2025, 6, 2, 23, 59, tzinfo=UTC))

    _backfill(dt.datetime(2025, 6, 10, 12, 0, tzinfo=UTC), days=1)
    snap = _fw_snapshots().get(recorded_at=MIDNIGHT)
    assert snap.value["by_type"] == {"2.8": 1}
