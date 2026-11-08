"""The feeder_report firmware rule: a feeder's own reported version outranks inferred identity."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

import pytest

from common.feeder_metrics import record_feeder_usage
from common.meshtastic_firmware import Evidence, classify, feeder_report_rule
from common.protocol import Protocol
from nodes.services.node_firmware import feeder_firmware_for, refresh_inferred_firmware
from nodes.services.observed_nodes import get_or_create_meshtastic_observed_node

pytestmark = pytest.mark.django_db

KEY_ID = 0x4396524C
OLD_NUM = 0xDA545C78
NUM = 0x1A2B3C4D


def _report(feeder, version, **kwargs):
    return record_feeder_usage(feeder, api="v4", reported_firmware=version, **kwargs)


def _fields(node):
    node.refresh_from_db()
    return node.inferred_firmware, node.inferred_firmware_basis


def test_rule_is_first_and_maps_versions():
    assert feeder_report_rule(Evidence(node_num=1, feeder_firmware="2.8.2.d5f1619")).generation == "2.8"
    assert feeder_report_rule(Evidence(node_num=1, feeder_firmware="2.9.1")).generation == "2.8"
    assert feeder_report_rule(Evidence(node_num=1, feeder_firmware="junk")) is None
    verdict = classify(Evidence(node_num=1, key_node_id=1, feeder_firmware="2.7.26"))
    assert (verdict.generation, verdict.basis) == ("2.7", "feeder_report")


def test_downgrade_is_visible(create_managed_node, create_observed_node):
    feeder = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=KEY_ID)
    row = create_observed_node(
        meshtastic_node_id=KEY_ID,
        meshtastic_key_node_id=KEY_ID,
        inferred_firmware="2.8",
        inferred_firmware_basis="key_identity",
    )

    _report(feeder, "2.7.26")

    assert _fields(row) == ("2.7", "feeder_report")


@pytest.mark.parametrize("version", ["2.8.2.d5f1619", "2.9.1"])
def test_2_8_and_later_read_2_8(create_managed_node, create_observed_node, version):
    feeder = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=NUM)
    row = create_observed_node(meshtastic_node_id=NUM)

    _report(feeder, version)

    assert _fields(row) == ("2.8", "feeder_report")


def test_after_an_upgrade_the_reported_number_is_used(create_managed_node, create_observed_node):
    feeder = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=OLD_NUM)
    old_row = create_observed_node(meshtastic_node_id=OLD_NUM)
    new_row = create_observed_node(meshtastic_node_id=KEY_ID)

    record_feeder_usage(feeder, api="v4", reported_node_num=KEY_ID, reported_firmware="2.8.2.d5f1619")

    assert _fields(new_row) == ("2.8", "feeder_report")
    assert _fields(old_row) == (None, None)


def test_a_later_nodeinfo_does_not_overwrite_feeder_report(create_managed_node, create_observed_node):
    feeder = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=OLD_NUM)
    row = create_observed_node(meshtastic_node_id=OLD_NUM)
    _report(feeder, "2.7.26")

    # What the NODEINFO path does: store a key, then refresh. The key says 2.8; the feeder says 2.7.
    row.refresh_from_db()
    row.meshtastic_key_node_id = OLD_NUM
    refresh_inferred_firmware(row)

    assert (row.inferred_firmware, row.inferred_firmware_basis) == ("2.7", "feeder_report")


def test_unparseable_version_falls_through_to_key_identity(create_managed_node, create_observed_node):
    feeder = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=NUM)
    row = create_observed_node(meshtastic_node_id=NUM, meshtastic_key_node_id=NUM)

    _report(feeder, "not-a-version")

    assert _fields(row) == ("2.8", "key_identity")


def test_no_evidence_and_no_report_stays_null(create_managed_node, create_observed_node):
    create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=NUM)
    row = create_observed_node(meshtastic_node_id=NUM)

    assert refresh_inferred_firmware(row) is False
    assert _fields(row) == (None, None)


def test_no_observed_row_yet_is_fine(create_managed_node):
    feeder = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=NUM)

    assert "reported_firmware_version" in _report(feeder, "2.8.2")


def test_soft_deleted_feeder_is_ignored(create_managed_node, create_observed_node):
    feeder = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=NUM)
    row = create_observed_node(meshtastic_node_id=NUM)
    _report(feeder, "2.7.26")
    feeder.deleted_at = timezone.now()
    feeder.save(update_fields=["deleted_at"])

    assert feeder_firmware_for(NUM) is None
    row.refresh_from_db()
    row.inferred_firmware = None
    row.inferred_firmware_basis = None
    assert refresh_inferred_firmware(row) is False


def test_newest_report_wins_when_two_feeders_share_a_number(create_managed_node):
    now = timezone.now()
    older = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=NUM)
    newer = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=OLD_NUM)
    _report(older, "2.7.26", now=now - timedelta(hours=1))
    record_feeder_usage(newer, api="v4", reported_node_num=NUM, reported_firmware="2.8.2", now=now)

    assert feeder_firmware_for(NUM) == "2.8.2"


def test_backfill_matches_ingest(create_managed_node, create_observed_node):
    feeder = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=OLD_NUM)
    # Report without an ObservedNode so ingest leaves nothing behind, then create the rows.
    record_feeder_usage(feeder, api="v4", reported_node_num=KEY_ID, reported_firmware="2.7.26")
    downgraded = create_observed_node(meshtastic_node_id=KEY_ID, meshtastic_key_node_id=KEY_ID)
    stale_number = create_observed_node(meshtastic_node_id=OLD_NUM)
    plain = create_observed_node(meshtastic_node_id=0x5555, meshtastic_key_node_id=0x5555)

    call_command("backfill_inferred_firmware", stdout=StringIO())

    assert _fields(downgraded) == ("2.7", "feeder_report")
    assert _fields(stale_number) == (None, None)
    assert _fields(plain) == ("2.8", "key_identity")

    # And the single-row path agrees.
    downgraded.inferred_firmware = None
    downgraded.inferred_firmware_basis = None
    refresh_inferred_firmware(downgraded)
    assert (downgraded.inferred_firmware, downgraded.inferred_firmware_basis) == ("2.7", "feeder_report")


def test_new_keyless_row_for_a_reporting_feeder_starts_as_feeder_report(create_managed_node):
    feeder = create_managed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=NUM)
    _report(feeder, "2.7.26")  # no ObservedNode exists for NUM yet

    row, created = get_or_create_meshtastic_observed_node(NUM)
    assert created
    assert _fields(row) == ("2.7", "feeder_report")

    other, _ = get_or_create_meshtastic_observed_node(NUM + 1)
    assert _fields(other) == (None, None)
