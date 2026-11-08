"""Tests for the backfill_inferred_firmware management command."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

import pytest

from common.protocol import Protocol
from nodes.models import ObservedNode

pytestmark = pytest.mark.django_db

KEY_HEX = "a0b3a9cf5a7b5bcfd38bc67488e5384ea6406150177b75309bc105fe6d732c5b"
KEY_ID = 0x4396524C  # crc32 of KEY_HEX
OLD_NUM = 0xDA545C78


def _run(*args):
    out = StringIO()
    call_command("backfill_inferred_firmware", *args, stdout=out)
    return out.getvalue()


def _seed(create_observed_node):
    """One row per outcome."""
    return {
        "2.8": create_observed_node(meshtastic_node_id=KEY_ID, meshtastic_key_node_id=KEY_ID),
        "2.7": create_observed_node(meshtastic_node_id=OLD_NUM, meshtastic_key_node_id=KEY_ID),
        "predicted": create_observed_node(meshtastic_node_id=777, meshtastic_key_node_id=None),
        "unknown": create_observed_node(meshtastic_node_id=888, meshtastic_key_node_id=None),
    }


def _fields(node):
    node.refresh_from_db()
    return node.inferred_firmware, node.inferred_firmware_basis


def test_each_outcome(create_observed_node):
    rows = _seed(create_observed_node)
    # The "predicted" row's number is another row's key-derived id.
    create_observed_node(meshtastic_node_id=0x1111, meshtastic_key_node_id=777)

    out = _run()

    assert _fields(rows["2.8"]) == ("2.8", "key_identity")
    assert _fields(rows["2.7"]) == ("2.7", "key_identity")
    assert _fields(rows["predicted"]) == ("2.8", "predicted_id")
    assert _fields(rows["unknown"]) == (None, None)
    assert "ObservedNode: scanned 5, updated 4" in out
    assert "By result: 2.7/key_identity 2, 2.8/key_identity 1, 2.8/predicted_id 1, unknown 1" in out


def test_second_run_updates_nothing_and_keeps_the_stamp(create_observed_node):
    rows = _seed(create_observed_node)
    _run()
    stamps = {k: ObservedNode.objects.get(pk=r.pk).inferred_firmware_at for k, r in rows.items()}

    out = _run()

    assert "updated 0" in out
    for key, row in rows.items():
        row.refresh_from_db()
        assert row.inferred_firmware_at == stamps[key]


def test_dry_run_writes_nothing_and_reports_the_same_counts(create_observed_node):
    rows = _seed(create_observed_node)

    dry = _run("--dry-run")

    assert all(_fields(row) == (None, None) for row in rows.values())
    assert all(row.inferred_firmware_at is None for row in rows.values())
    real = _run()
    assert dry.replace("[dry-run] ", "") == real
    assert all(line.startswith("[dry-run] ") for line in dry.strip().splitlines())


def test_small_batches_cover_every_row(create_observed_node):
    rows = _seed(create_observed_node)

    out = _run("--batch-size", "1")

    assert "scanned 4, updated 2" in out
    assert _fields(rows["2.8"]) == ("2.8", "key_identity")


def test_meshcore_rows_are_untouched(create_observed_node):
    node = create_observed_node(protocol=Protocol.MESHCORE, meshtastic_node_id=None, meshtastic_key_node_id=KEY_ID)

    out = _run()

    assert "scanned 0" in out
    assert _fields(node) == (None, None)


def test_no_evidence_never_clears_a_stored_verdict(create_observed_node):
    node = create_observed_node(inferred_firmware="2.8", inferred_firmware_basis="feeder_report")

    out = _run()

    assert _fields(node) == ("2.8", "feeder_report")
    assert "updated 0" in out
    assert "2.8/feeder_report 1" in out


def test_active_key_coverage_line(create_observed_node):
    now = timezone.now()
    create_observed_node(meshtastic_node_id=1, meshtastic_key_node_id=KEY_ID, last_heard=now - timedelta(hours=1))
    create_observed_node(meshtastic_node_id=2, meshtastic_key_node_id=None, last_heard=now - timedelta(hours=167))
    create_observed_node(meshtastic_node_id=3, meshtastic_key_node_id=None, last_heard=now - timedelta(hours=1))
    create_observed_node(meshtastic_node_id=4, meshtastic_key_node_id=None, last_heard=now - timedelta(hours=200))
    create_observed_node(meshtastic_node_id=5, meshtastic_key_node_id=KEY_ID, last_heard=None)

    out = _run()

    assert "Active in the last 168h: 3, with a usable key 1 (33.3%)" in out


def test_coverage_line_with_no_active_nodes(create_observed_node):
    out = _run()

    assert "Active in the last 168h: 0, with a usable key 0 (0.0%)" in out
