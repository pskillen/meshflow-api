"""Feeder re-key decision logic (ID-4): nodes.services.feeder_identity."""

from unittest import mock

from django.db import IntegrityError

import pytest

from common.meshtastic_identity import key_node_id, normalise_pubkey
from common.protocol import Protocol
from nodes.models import ManagedNode, ManagedNodeIdentityEvent, ObservedNode
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
    return create_managed_node(meshtastic_node_id=OLD_NUM, name="Feeder")


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
    feeder.meshtastic_public_key = KEY_HEX
    feeder.save()
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
def test_trust_on_first_use(rekey_on, feeder):
    assert not feeder.meshtastic_public_key
    event = _apply(feeder)
    assert event.outcome == Outcome.AUTO_UPDATED
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == NEW_NUM
    assert feeder.meshtastic_public_key == KEY_HEX


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
    ensure.assert_called_once_with(feeder)
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
def test_unchanged_number_fills_blank_key_silently(feeder):
    assert _apply(feeder, num=OLD_NUM) is None
    feeder.refresh_from_db()
    assert feeder.meshtastic_public_key == KEY_HEX
    assert feeder.meshtastic_key_node_id == key_node_id(KEY_HEX)
    assert feeder.identity_events.count() == 0


@pytest.mark.django_db
def test_unchanged_number_different_key_is_key_changed(settings, feeder):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False  # not gated by the flag
    feeder.meshtastic_public_key = OTHER_KEY_HEX
    feeder.save()
    event = _apply(feeder, num=OLD_NUM)
    assert event.outcome == Outcome.KEY_CHANGED
    assert event.old_meshtastic_node_id == event.new_meshtastic_node_id == OLD_NUM
    feeder.refresh_from_db()
    assert feeder.meshtastic_public_key == KEY_HEX
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
    feeder.meshtastic_public_key = KEY_HEX
    feeder.save()
    with mock.patch.object(ManagedNode.objects, "filter", wraps=ManagedNode.objects.filter) as flt:
        assert _apply(feeder, num=OLD_NUM) is None
    assert feeder.identity_events.count() == 0
    # no update() on the feeder row
    assert not any(c for c in flt.mock_calls if "update" in str(c))


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
