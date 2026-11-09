"""Feeder re-key decision logic (ID-4): nodes.services.feeder_identity."""

import runpy
from datetime import timedelta
from unittest import mock

from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import pytest

from common.meshtastic_identity import key_node_id, normalise_pubkey
from common.protocol import Protocol
from Meshflow.settings import base as settings_base
from nodes.models import ManagedNode, ManagedNodeIdentityEvent, NodeOwnerClaim, ObservedNode
from nodes.services.feeder_identity import apply_reported_identity
from nodes.signals import feeder_identity_changed

Outcome = ManagedNodeIdentityEvent.Outcome
Reason = ManagedNodeIdentityEvent.Reason

# docs/packets/nodeinfo_packet.json: the key broadcast by !da545c78, which predicts !4396524c on 2.8.
OLD_NUM = 0xDA545C78
NEW_NUM = 0x4396524C
KEY_B64 = "oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs="
KEY_HEX = normalise_pubkey(KEY_B64)
OTHER_KEY_HEX = "ab" * 32


@pytest.fixture
def rekey_on(settings):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True


@pytest.fixture
def feeder(create_managed_node):
    """A feeder whose key is already held (as the backfill leaves it)."""
    return create_managed_node(meshtastic_node_id=OLD_NUM, name="Feeder", meshtastic_public_key=KEY_HEX)


@pytest.fixture
def keyless_feeder(create_managed_node):
    return create_managed_node(meshtastic_node_id=OLD_NUM, name="Keyless")


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(username="someone-else", password="x", email="else@example.com")


@pytest.fixture
def received():
    calls = []

    def handler(sender, **kwargs):
        calls.append(kwargs)

    feeder_identity_changed.connect(handler)
    yield calls
    feeder_identity_changed.disconnect(handler)


def _apply(node, num=NEW_NUM, key=KEY_B64):
    return apply_reported_identity(node, reported_node_num=num, reported_pubkey=key)


def _events(node):
    return list(node.identity_events.order_by("id"))


def test_example_key_predicts_new_number():
    assert key_node_id(KEY_HEX) == NEW_NUM


@pytest.mark.django_db
def test_auto_update_applies(rekey_on, feeder, received, create_observed_node):
    pk = feeder.pk

    event = _apply(feeder)

    feeder.refresh_from_db()
    assert feeder.pk == pk
    assert feeder.meshtastic_node_id == NEW_NUM
    assert feeder.meshtastic_public_key == KEY_HEX
    assert feeder.meshtastic_key_node_id == NEW_NUM
    events = _events(feeder)
    assert events == [event]
    assert (event.outcome, event.old_meshtastic_node_id, event.new_meshtastic_node_id) == (
        Outcome.AUTO_UPDATED,
        OLD_NUM,
        NEW_NUM,
    )
    assert event.reported_public_key == KEY_HEX
    assert len(received) == 1
    assert received[0]["old_node_id"] == OLD_NUM and received[0]["new_node_id"] == NEW_NUM
    assert received[0]["event"] == event
    assert ManagedNode.objects.filter(pk=pk).count() == 1


@pytest.mark.django_db
def test_in_memory_node_updated(rekey_on, feeder):
    _apply(feeder)
    assert feeder.meshtastic_node_id == NEW_NUM
    assert feeder.meshtastic_public_key == KEY_HEX


@pytest.mark.django_db
def test_apply_ensures_and_claims_observed_node(rekey_on, feeder):
    assert not ObservedNode.objects.filter(meshtastic_node_id=NEW_NUM).exists()
    with mock.patch(
        "nodes.services.feeder_identity.ensure_observed_node_for_managed_node",
        wraps=__import__(
            "nodes.managed_node_bootstrap", fromlist=["ensure_observed_node_for_managed_node"]
        ).ensure_observed_node_for_managed_node,
    ) as ensure:
        _apply(feeder)
    ensure.assert_called_once_with(feeder, claim=True)
    observed = ObservedNode.objects.get(meshtastic_node_id=NEW_NUM)
    assert observed.claimed_by_id == feeder.owner_id


@pytest.mark.parametrize(
    "case, reason",
    [
        ("no_key", Reason.KEY_NOT_REPORTED),
        ("crc", Reason.CRC_MISMATCH),
        ("stored_other", Reason.KEY_MISMATCH),
        ("observed_clone", Reason.SHARED_KEY),
        ("collision", Reason.NUMBER_COLLISION),
        ("flag_off", Reason.AUTO_REKEY_DISABLED),
    ],
)
@pytest.mark.django_db
def test_flag_rows(settings, create_managed_node, create_observed_node, feeder, case, reason):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = case != "flag_off"
    num, key = NEW_NUM, KEY_B64
    if case == "no_key":
        key = None
    elif case == "crc":
        num = NEW_NUM + 1
    elif case == "stored_other":
        feeder.meshtastic_public_key = OTHER_KEY_HEX
        feeder.save()
    elif case == "observed_clone":
        create_observed_node(meshtastic_node_id=0x11111111, meshtastic_public_key_hex=KEY_HEX)
    elif case == "collision":
        create_managed_node(meshtastic_node_id=NEW_NUM, name="Other")

    event = _apply(feeder, num=num, key=key)

    assert event.outcome == Outcome.FLAGGED
    assert event.reason == reason
    assert event.new_meshtastic_node_id == num
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_second_managed_node_with_key_is_shared(rekey_on, create_managed_node, feeder):
    create_managed_node(meshtastic_node_id=0x22222222, meshtastic_public_key=KEY_HEX, name="Clone")
    assert _apply(feeder).reason == Reason.SHARED_KEY


@pytest.mark.django_db
def test_soft_deleted_managed_node_does_not_count(rekey_on, create_managed_node, feeder):
    from django.utils import timezone

    create_managed_node(
        meshtastic_node_id=0x22222222, meshtastic_public_key=KEY_HEX, name="Gone", deleted_at=timezone.now()
    )
    assert _apply(feeder).outcome == Outcome.AUTO_UPDATED


@pytest.mark.django_db
def test_own_observed_rows_do_not_count(rekey_on, create_observed_node, feeder):
    create_observed_node(meshtastic_node_id=OLD_NUM, meshtastic_public_key_hex=KEY_HEX)
    create_observed_node(meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=KEY_HEX)
    assert _apply(feeder).outcome == Outcome.AUTO_UPDATED


@pytest.mark.django_db
def test_flag_dedupe(settings, feeder):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False
    first = _apply(feeder)
    assert first.reason == Reason.AUTO_REKEY_DISABLED
    assert _apply(feeder) is None
    assert feeder.identity_events.count() == 1


@pytest.mark.django_db
def test_flag_change_resolves_old_row(settings, feeder):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False
    old = _apply(feeder)
    new = _apply(feeder, num=NEW_NUM + 1)  # crc mismatch now
    assert new.reason == Reason.CRC_MISMATCH
    old.refresh_from_db()
    assert old.resolved_at is not None
    assert new.resolved_at is None


@pytest.mark.django_db
def test_enabling_flag_resolves_flag_and_applies(settings, feeder):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False
    flagged = _apply(feeder)
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    applied = _apply(feeder)
    flagged.refresh_from_db()
    assert flagged.resolved_at is not None
    assert applied.outcome == Outcome.AUTO_UPDATED
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == NEW_NUM


@pytest.mark.django_db
def test_unchanged_number_records_first_key_with_audit_event(keyless_feeder):
    event = _apply(keyless_feeder, num=OLD_NUM)
    assert event.outcome == Outcome.KEY_CHANGED
    assert event.reported_public_key == KEY_HEX
    keyless_feeder.refresh_from_db()
    assert keyless_feeder.meshtastic_public_key == KEY_HEX
    assert keyless_feeder.meshtastic_key_node_id == key_node_id(KEY_HEX)


@pytest.mark.django_db
def test_unchanged_number_different_key_is_flagged_and_not_stored(settings, feeder):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False  # not gated by the flag
    feeder.meshtastic_public_key = OTHER_KEY_HEX
    feeder.save()
    event = _apply(feeder, num=OLD_NUM)
    assert (event.outcome, event.reason) == (Outcome.FLAGGED, Reason.KEY_MISMATCH)
    assert event.old_meshtastic_node_id == event.new_meshtastic_node_id == OLD_NUM
    feeder.refresh_from_db()
    assert feeder.meshtastic_public_key == OTHER_KEY_HEX
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_unchanged_number_key_mismatch_stays_open_and_dedupes(feeder):
    feeder.meshtastic_public_key = OTHER_KEY_HEX
    feeder.save()
    event = _apply(feeder, num=OLD_NUM)
    assert _apply(feeder, num=OLD_NUM) is None
    event.refresh_from_db()
    assert event.resolved_at is None
    assert feeder.identity_events.count() == 1


@pytest.mark.django_db
def test_forged_key_cannot_become_trusted_via_unchanged_number(rekey_on, feeder):
    """The verifier's attack: replace the stored key on the old number, then claim the number the key hashes to."""
    feeder.meshtastic_public_key = OTHER_KEY_HEX
    feeder.save()
    _apply(feeder, num=OLD_NUM)
    assert _apply(feeder).reason == Reason.KEY_MISMATCH
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_blank_key_never_applies_on_the_changing_report(rekey_on, keyless_feeder):
    event = _apply(keyless_feeder)
    assert event.reason == Reason.KEY_MISMATCH
    keyless_feeder.refresh_from_db()
    assert keyless_feeder.meshtastic_node_id == OLD_NUM
    assert not keyless_feeder.meshtastic_public_key


@pytest.mark.django_db
def test_first_key_does_not_vouch_for_the_next_report(rekey_on, keyless_feeder):
    _apply(keyless_feeder, num=OLD_NUM)
    assert _apply(keyless_feeder).reason == Reason.KEY_MISMATCH
    keyless_feeder.refresh_from_db()
    assert keyless_feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_first_key_applies_once_settled(rekey_on, keyless_feeder):
    recorded = _apply(keyless_feeder, num=OLD_NUM)
    flagged = _apply(keyless_feeder)
    ManagedNodeIdentityEvent.objects.filter(pk=recorded.pk).update(created_at=timezone.now() - timedelta(hours=2))
    assert _apply(keyless_feeder).outcome == Outcome.AUTO_UPDATED
    flagged.refresh_from_db()
    assert flagged.resolved_at is not None


def _settled_report_key(feeder):
    """Record ``KEY_HEX`` from a report on the unchanged number and age it past the settle window."""
    recorded = _apply(feeder, num=OLD_NUM)
    ManagedNodeIdentityEvent.objects.filter(pk=recorded.pk).update(created_at=timezone.now() - timedelta(hours=2))


@pytest.mark.django_db
def test_key_from_report_applies_without_claiming_existing_target(rekey_on, keyless_feeder, create_observed_node):
    target = create_observed_node(meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=None, claimed_by=None)
    _settled_report_key(keyless_feeder)

    assert _apply(keyless_feeder).outcome == Outcome.AUTO_UPDATED

    target.refresh_from_db()
    assert target.claimed_by_id is None


@pytest.mark.django_db
def test_key_from_report_creates_target_unclaimed(rekey_on, keyless_feeder):
    _settled_report_key(keyless_feeder)

    assert _apply(keyless_feeder).outcome == Outcome.AUTO_UPDATED

    assert ObservedNode.objects.get(meshtastic_node_id=NEW_NUM).claimed_by_id is None


@pytest.mark.django_db
def test_key_from_report_leaves_owners_existing_claim(rekey_on, keyless_feeder, create_observed_node):
    target = create_observed_node(
        meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=None, claimed_by=keyless_feeder.owner
    )
    _settled_report_key(keyless_feeder)

    assert _apply(keyless_feeder).outcome == Outcome.AUTO_UPDATED

    target.refresh_from_db()
    assert target.claimed_by_id == keyless_feeder.owner_id


@pytest.mark.django_db
def test_first_key_contradicting_own_observed_row_is_flagged(keyless_feeder, create_observed_node):
    create_observed_node(meshtastic_node_id=OLD_NUM, meshtastic_public_key_hex=OTHER_KEY_HEX)
    assert _apply(keyless_feeder, num=OLD_NUM).reason == Reason.KEY_MISMATCH
    keyless_feeder.refresh_from_db()
    assert not keyless_feeder.meshtastic_public_key


@pytest.mark.django_db
def test_target_with_different_key_is_flagged(rekey_on, feeder, create_observed_node):
    create_observed_node(meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=OTHER_KEY_HEX)
    assert _apply(feeder).reason == Reason.KEY_MISMATCH
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_target_without_a_key_applies(rekey_on, feeder, create_observed_node):
    create_observed_node(meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=None, claimed_by=None)
    assert _apply(feeder).outcome == Outcome.AUTO_UPDATED


@pytest.mark.django_db
def test_target_claimed_by_someone_else_is_flagged(rekey_on, feeder, create_observed_node, other_user):
    create_observed_node(meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=KEY_HEX, claimed_by=other_user)
    assert _apply(feeder).reason == Reason.NUMBER_COLLISION
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_target_claimed_by_owner_applies(rekey_on, feeder, create_observed_node):
    create_observed_node(meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=KEY_HEX, claimed_by=feeder.owner)
    assert _apply(feeder).outcome == Outcome.AUTO_UPDATED


@pytest.mark.parametrize("accepted, flagged", [(True, True), (False, False)])
@pytest.mark.django_db
def test_target_accepted_claim_by_someone_else(rekey_on, feeder, create_observed_node, other_user, accepted, flagged):
    target = create_observed_node(meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=KEY_HEX, claimed_by=None)
    NodeOwnerClaim.objects.create(
        node=target, user=other_user, claim_key="k", accepted_at=timezone.now() if accepted else None
    )
    event = _apply(feeder)
    assert event.reason == Reason.NUMBER_COLLISION if flagged else event.outcome == Outcome.AUTO_UPDATED


@pytest.mark.parametrize("num, applied", [(0, False), (3, False), (0xFFFFFFFF, False), (4, True), (0xFFFFFFFE, True)])
@pytest.mark.django_db
def test_node_number_range(rekey_on, feeder, num, applied):
    with mock.patch("nodes.services.feeder_identity.key_node_id", return_value=num):
        event = _apply(feeder, num=num)
    feeder.refresh_from_db()
    if applied:
        assert feeder.meshtastic_node_id == num
    else:
        assert event.reason == Reason.NUMBER_COLLISION
        assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_unchanged_number_resolves_open_flagged(settings, feeder):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False
    flagged = _apply(feeder)
    assert _apply(feeder, num=OLD_NUM, key=None) is None
    flagged.refresh_from_db()
    assert flagged.resolved_at is not None


@pytest.mark.django_db
def test_downgrade_same_number_same_key_writes_nothing(feeder):
    with CaptureQueriesContext(connection) as queries:
        assert _apply(feeder, num=OLD_NUM) is None
    assert feeder.identity_events.count() == 0
    writes = [q["sql"] for q in queries if q["sql"].lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE"))]
    # Resolving open flagged rows is allowed; nothing may touch the feeder row.
    assert not [sql for sql in writes if "nodes_managednode" in sql and "identityevent" not in sql]
    assert not [sql for sql in writes if sql.lstrip().upper().startswith("INSERT")]


@pytest.mark.django_db
def test_concurrent_apply_writes_nothing(rekey_on, feeder, received):
    stale = ManagedNode.objects.get(pk=feeder.pk)
    stale.meshtastic_node_id = NEW_NUM  # another request already applied it
    with mock.patch("nodes.services.feeder_identity._lock", return_value=stale):
        assert _apply(feeder) is None
    assert feeder.identity_events.count() == 0
    assert received == []
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_integrity_error_becomes_number_collision(rekey_on, feeder, received):
    with mock.patch.object(ManagedNode, "save", side_effect=IntegrityError("unique")):
        event = _apply(feeder)
    assert event.outcome == Outcome.FLAGGED
    assert event.reason == Reason.NUMBER_COLLISION
    assert received == []
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_meshcore_node_ignored(create_managed_node):
    node = create_managed_node(protocol=Protocol.MESHCORE)
    assert apply_reported_identity(node, reported_node_num=5, reported_pubkey=KEY_B64) is None
    assert not ManagedNodeIdentityEvent.objects.exists()


@pytest.mark.django_db
def test_metric_counted(rekey_on, feeder):
    from nodes.services.feeder_identity import FEEDER_IDENTITY_CHANGES

    child = FEEDER_IDENTITY_CHANGES.labels(protocol="meshtastic", outcome="auto_updated")
    before = child._value.get()
    _apply(feeder)
    assert child._value.get() == before + 1


@pytest.mark.django_db
def test_flagged_and_first_key_metrics_counted(settings, keyless_feeder):
    from nodes.services.feeder_identity import FEEDER_IDENTITY_CHANGES

    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False
    key_changed = FEEDER_IDENTITY_CHANGES.labels(protocol="meshtastic", outcome="key_changed")
    flagged = FEEDER_IDENTITY_CHANGES.labels(protocol="meshtastic", outcome="flagged")
    before = key_changed._value.get(), flagged._value.get()
    _apply(keyless_feeder, num=OLD_NUM)
    _apply(keyless_feeder)
    assert (key_changed._value.get(), flagged._value.get()) == (before[0] + 1, before[1] + 1)


@pytest.mark.parametrize(
    "open_row",
    [
        pytest.param({"new_meshtastic_node_id": NEW_NUM + 1}, id="number"),
        pytest.param({"reported_public_key": OTHER_KEY_HEX}, id="key"),
        pytest.param({"reason": Reason.SHARED_KEY}, id="reason"),
    ],
)
@pytest.mark.django_db
def test_dedupe_needs_every_component_to_match(settings, feeder, open_row):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False
    first = _apply(feeder)
    feeder.identity_events.filter(pk=first.pk).update(**open_row)
    assert _apply(feeder).reason == Reason.AUTO_REKEY_DISABLED
    assert feeder.identity_events.count() == 2


@pytest.mark.django_db
def test_collision_reported_before_flag_off(settings, create_managed_node, feeder):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False
    create_managed_node(meshtastic_node_id=NEW_NUM, name="Other")
    assert _apply(feeder).reason == Reason.NUMBER_COLLISION


@pytest.mark.django_db
def test_soft_deleted_feeders_number_is_free(rekey_on, create_managed_node, feeder):
    create_managed_node(meshtastic_node_id=NEW_NUM, name="Gone", deleted_at=timezone.now())
    assert _apply(feeder).outcome == Outcome.AUTO_UPDATED


@pytest.mark.django_db
def test_failing_ensure_still_sends_signal(rekey_on, feeder, received):
    with mock.patch("nodes.services.feeder_identity.ensure_observed_node_for_managed_node", side_effect=RuntimeError):
        event = _apply(feeder)
    assert event.outcome == Outcome.AUTO_UPDATED
    assert len(received) == 1


@pytest.mark.django_db
def test_failing_receiver_does_not_block_others_or_the_caller(rekey_on, feeder, received):
    def bad(sender, **kwargs):
        raise RuntimeError("receiver failed")

    feeder_identity_changed.connect(bad)
    try:
        event = _apply(feeder)
    finally:
        feeder_identity_changed.disconnect(bad)
    assert event.outcome == Outcome.AUTO_UPDATED
    assert len(received) == 1


def test_auto_rekey_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("MESHTASTIC_FEEDER_AUTO_REKEY", raising=False)
    assert runpy.run_path(settings_base.__file__)["MESHTASTIC_FEEDER_AUTO_REKEY"] is False
