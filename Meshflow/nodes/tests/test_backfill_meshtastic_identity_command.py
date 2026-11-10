"""Tests for the backfill_meshtastic_identity management command."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.utils import timezone

import pytest

from common.meshtastic_identity import key_node_id
from nodes.models import ManagedNode, ObservedNode

pytest_plugins = ["packets.tests.conftest"]

KEY_B64 = "oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs="
KEY_HEX = "a0b3a9cf5a7b5bcfd38bc67488e5384ea6406150177b75309bc105fe6d732c5b"
OTHER_KEY_B64 = "c1OCe93DrrJwtPKC5VJbneJIrK37WxHBZyPkrYTI/nw="


@pytest.fixture
def allow_duplicates(db):
    """The unique index forbids duplicate rows; these tests rebuild a pre-constraint database (rolled back after)."""
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX nodes_observednode_mt_node_id_unique")


def _run(*args):
    out = StringIO()
    call_command("backfill_meshtastic_identity", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_backfill_sets_observed_fields_from_base64_and_hex(create_observed_node):
    b64_node = create_observed_node(meshtastic_node_id=1001, meshtastic_public_key=KEY_B64)
    hex_node = create_observed_node(meshtastic_node_id=1002, meshtastic_public_key=OTHER_KEY_B64)
    hex_node.meshtastic_public_key = KEY_HEX
    hex_node.save()

    _run()

    b64_node.refresh_from_db()
    hex_node.refresh_from_db()
    assert b64_node.meshtastic_public_key_hex == KEY_HEX
    assert b64_node.meshtastic_key_node_id == 0x4396524C
    assert hex_node.meshtastic_public_key_hex == KEY_HEX
    assert hex_node.meshtastic_key_node_id == 0x4396524C


@pytest.mark.django_db
def test_backfill_malformed_key_gives_null_not_error(create_observed_node):
    node = create_observed_node(meshtastic_node_id=1003, meshtastic_public_key="garbage")

    _run()

    node.refresh_from_db()
    assert node.meshtastic_public_key_hex is None
    assert node.meshtastic_key_node_id is None


@pytest.mark.django_db
def test_backfill_falls_back_to_latest_node_info_packet(create_observed_node, create_node_info_packet):
    node = create_observed_node(meshtastic_node_id=1004, meshtastic_public_key=None)
    now = timezone.now()
    create_node_info_packet(
        from_int=1004, public_key=OTHER_KEY_B64, first_reported_time=now - timedelta(days=2), packet_id=1
    )
    create_node_info_packet(from_int=1004, public_key=KEY_B64, first_reported_time=now, packet_id=2)
    create_node_info_packet(from_int=1004, public_key=None, first_reported_time=now + timedelta(days=1), packet_id=3)

    out = _run()

    node.refresh_from_db()
    assert node.meshtastic_public_key_hex == KEY_HEX
    assert node.meshtastic_key_node_id == key_node_id(KEY_B64)
    assert "fallback 1" in out
    # The stored (raw) key column is left alone; only the derived columns are written.
    assert node.meshtastic_public_key is None


@pytest.mark.django_db
def test_backfill_sets_managed_node_key_from_observed_node(create_observed_node, create_managed_node):
    create_observed_node(meshtastic_node_id=2001, meshtastic_public_key=KEY_B64)
    managed = create_managed_node(meshtastic_node_id=2001)
    unmatched = create_managed_node(meshtastic_node_id=2002)

    _run()

    managed.refresh_from_db()
    unmatched.refresh_from_db()
    assert managed.meshtastic_public_key == KEY_HEX
    assert managed.meshtastic_key_node_id == 0x4396524C
    assert unmatched.meshtastic_public_key is None
    assert unmatched.meshtastic_key_node_id is None


@pytest.mark.django_db
def test_backfilled_managed_key_is_dated_so_it_cannot_back_a_number_change_at_once(
    create_observed_node, create_managed_node, settings
):
    """The key comes from the client-writable observed row: it gets the same settle hour as a key from a report."""
    from nodes.models import ManagedNodeIdentityEvent
    from nodes.services.feeder_identity import FIRST_KEY_SETTLE, apply_reported_identity

    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    create_observed_node(meshtastic_node_id=2010, meshtastic_public_key=KEY_B64)
    managed = create_managed_node(meshtastic_node_id=2010)

    _run()

    event = managed.identity_events.get()
    assert event.outcome == ManagedNodeIdentityEvent.Outcome.KEY_CHANGED
    assert event.reported_public_key == KEY_HEX
    managed.refresh_from_db()
    now = timezone.now()
    flagged = apply_reported_identity(managed, reported_node_num=0x4396524C, reported_pubkey=KEY_B64, now=now)
    assert flagged.reason == ManagedNodeIdentityEvent.Reason.KEY_MISMATCH
    later = now + FIRST_KEY_SETTLE + timedelta(minutes=1)
    applied = apply_reported_identity(managed, reported_node_num=0x4396524C, reported_pubkey=KEY_B64, now=later)
    assert applied.outcome == ManagedNodeIdentityEvent.Outcome.AUTO_UPDATED


@pytest.mark.django_db
def test_backfill_writes_no_event_when_the_managed_key_was_already_held(create_observed_node, create_managed_node):
    create_observed_node(meshtastic_node_id=2011, meshtastic_public_key=KEY_B64)
    managed = create_managed_node(meshtastic_node_id=2011)
    ManagedNode.objects.filter(pk=managed.pk).update(meshtastic_public_key=KEY_HEX)

    _run()

    assert not managed.identity_events.exists()


@pytest.mark.django_db
def test_dry_run_writes_no_identity_events(create_observed_node, create_managed_node):
    create_observed_node(meshtastic_node_id=2012, meshtastic_public_key=KEY_B64)
    managed = create_managed_node(meshtastic_node_id=2012)

    _run("--dry-run")

    assert not managed.identity_events.exists()


@pytest.mark.django_db
def test_backfill_does_not_clear_an_existing_managed_key(create_observed_node, create_managed_node):
    create_observed_node(meshtastic_node_id=2003, meshtastic_public_key=None)
    managed = create_managed_node(meshtastic_node_id=2003)
    ManagedNode.objects.filter(pk=managed.pk).update(meshtastic_public_key=KEY_HEX, meshtastic_key_node_id=0x4396524C)

    _run()

    managed.refresh_from_db()
    assert managed.meshtastic_public_key == KEY_HEX


@pytest.mark.django_db
def test_backfill_never_replaces_a_stored_managed_key(create_observed_node, create_managed_node):
    create_observed_node(meshtastic_node_id=2004, meshtastic_public_key=OTHER_KEY_B64)
    managed = create_managed_node(meshtastic_node_id=2004)
    ManagedNode.objects.filter(pk=managed.pk).update(meshtastic_public_key=KEY_HEX, meshtastic_key_node_id=0x4396524C)

    _run()

    managed.refresh_from_db()
    assert managed.meshtastic_public_key == KEY_HEX
    assert managed.meshtastic_key_node_id == 0x4396524C


@pytest.mark.django_db
def test_backfill_is_idempotent(create_observed_node, create_managed_node):
    create_observed_node(meshtastic_node_id=3001, meshtastic_public_key=KEY_B64)
    create_managed_node(meshtastic_node_id=3001)

    first = _run()
    snapshot = list(ObservedNode.objects.values_list("pk", "meshtastic_public_key_hex", "meshtastic_key_node_id"))
    managed_snapshot = list(ManagedNode.objects.values_list("pk", "meshtastic_public_key", "meshtastic_key_node_id"))
    second = _run()

    assert "ObservedNode: scanned 1, updated 1" in first
    assert "ObservedNode: scanned 1, updated 0" in second
    assert "ManagedNode: scanned 1, updated 0" in second
    assert snapshot == list(
        ObservedNode.objects.values_list("pk", "meshtastic_public_key_hex", "meshtastic_key_node_id")
    )
    assert managed_snapshot == list(
        ManagedNode.objects.values_list("pk", "meshtastic_public_key", "meshtastic_key_node_id")
    )


@pytest.mark.django_db
def test_dry_run_writes_nothing_but_reports(create_observed_node, create_managed_node):
    node = create_observed_node(meshtastic_node_id=4001, meshtastic_public_key=KEY_B64)
    managed = create_managed_node(meshtastic_node_id=4001)

    out = _run("--dry-run")

    node.refresh_from_db()
    managed.refresh_from_db()
    assert node.meshtastic_public_key_hex is None
    assert node.meshtastic_key_node_id is None
    assert managed.meshtastic_public_key is None
    assert "[dry-run]" in out
    assert "ObservedNode: scanned 1, updated 1" in out


@pytest.mark.django_db
def test_backfill_batches(create_observed_node):
    for i in range(5):
        create_observed_node(meshtastic_node_id=5000 + i, meshtastic_public_key=KEY_B64)

    out = _run("--batch-size", "2")

    assert "ObservedNode: scanned 5, updated 5" in out
    assert ObservedNode.objects.filter(meshtastic_key_node_id=0x4396524C).count() == 5


@pytest.mark.django_db
def test_backfill_reports_shared_keys(create_observed_node):
    create_observed_node(meshtastic_node_id=6001, meshtastic_public_key=KEY_B64)
    create_observed_node(meshtastic_node_id=6002, meshtastic_public_key=KEY_B64)
    create_observed_node(meshtastic_node_id=6003, meshtastic_public_key=OTHER_KEY_B64)

    out = _run()

    assert "Shared keys: 1 key(s)" in out
    assert "!00001771, !00001772" in out
    assert "2 nodes" in out


def _managed_and_shared_lines(out):
    keep = ("ManagedNode:", "Shared keys", "  ", "Duplicate")
    lines = [line.replace("[dry-run] ", "") for line in out.splitlines()]
    return [line for line in lines if line.startswith(keep)]


@pytest.mark.django_db
def test_dry_run_managed_and_shared_output_matches_real_run(create_observed_node, create_managed_node):
    create_observed_node(meshtastic_node_id=7001, meshtastic_public_key=KEY_B64)
    create_observed_node(meshtastic_node_id=7002, meshtastic_public_key=KEY_B64)
    create_observed_node(meshtastic_node_id=7003, meshtastic_public_key=None)
    managed = create_managed_node(meshtastic_node_id=7001)
    create_managed_node(meshtastic_node_id=7003)

    dry = _run("--dry-run")
    managed.refresh_from_db()
    assert managed.meshtastic_public_key is None
    assert ObservedNode.objects.filter(meshtastic_public_key_hex__isnull=False).count() == 0

    real = _run()

    assert "ManagedNode: scanned 2, updated 1, no matching observed key 1" in dry
    assert "Shared keys: 1 key(s)" in dry
    assert _managed_and_shared_lines(dry) == _managed_and_shared_lines(real)
    managed.refresh_from_db()
    assert managed.meshtastic_public_key == KEY_HEX


@pytest.mark.django_db
def test_duplicate_rows_for_one_number_are_not_a_shared_key(allow_duplicates, create_observed_node):
    create_observed_node(meshtastic_node_id=8001, meshtastic_public_key=KEY_B64)
    create_observed_node(meshtastic_node_id=8001, meshtastic_public_key=KEY_B64)

    out = _run()

    assert "Shared keys: none" in out
    assert "Duplicate ObservedNode rows (same node number, several rows): 1" in out


@pytest.mark.django_db
def test_two_numbers_with_one_key_are_shared_and_listed_once(allow_duplicates, create_observed_node):
    create_observed_node(meshtastic_node_id=8101, meshtastic_public_key=KEY_B64)
    create_observed_node(meshtastic_node_id=8101, meshtastic_public_key=KEY_B64)
    create_observed_node(meshtastic_node_id=8102, meshtastic_public_key=KEY_B64)

    out = _run()

    assert "Shared keys: 1 key(s)" in out
    assert "2 nodes (!00001fa5, !00001fa6)" in out
    assert out.count("!00001fa5") == 1


@pytest.mark.django_db
def test_managed_choice_among_duplicate_rows_prefers_key_then_latest_heard(
    allow_duplicates, create_observed_node, create_managed_node
):
    now = timezone.now()
    keyed_old = create_observed_node(meshtastic_node_id=8201, meshtastic_public_key=KEY_B64)
    keyless_new = create_observed_node(meshtastic_node_id=8201, meshtastic_public_key=None)
    ObservedNode.objects.filter(pk=keyed_old.pk).update(last_heard=now - timedelta(days=5))
    ObservedNode.objects.filter(pk=keyless_new.pk).update(last_heard=now)
    other_old = create_observed_node(meshtastic_node_id=8202, meshtastic_public_key=OTHER_KEY_B64)
    other_new = create_observed_node(meshtastic_node_id=8202, meshtastic_public_key=KEY_B64)
    ObservedNode.objects.filter(pk=other_old.pk).update(last_heard=now - timedelta(days=5))
    ObservedNode.objects.filter(pk=other_new.pk).update(last_heard=now)
    m1 = create_managed_node(meshtastic_node_id=8201)
    m2 = create_managed_node(meshtastic_node_id=8202)

    _run()

    m1.refresh_from_db()
    m2.refresh_from_db()
    assert m1.meshtastic_public_key == KEY_HEX
    assert m2.meshtastic_public_key == KEY_HEX
