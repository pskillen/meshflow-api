"""Feeder number change API (ID-4): manual re-point, event list and acknowledge."""

import base64
from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

import nodes.tests.conftest  # noqa: F401
from common.meshtastic_identity import key_node_id, normalise_pubkey
from common.protocol import Protocol
from nodes.models import ManagedNode, ManagedNodeIdentityEvent, ObservedNode
from nodes.services.feeder_identity import apply_reported_identity
from nodes.signals import feeder_identity_changed

Outcome = ManagedNodeIdentityEvent.Outcome
Reason = ManagedNodeIdentityEvent.Reason

OLD_NUM = 0xDA545C78
NEW_NUM = 0x4396524C
KEY_HEX = normalise_pubkey("oLOpz1p7W8/Ti8Z0iOU4TqZAYVAXe3Uwm8EF/m1zLFs=")
OTHER_KEY_HEX = normalise_pubkey(base64.b64encode(b"\x01" * 32).decode())

LIST_URL = "managed-node-identity-events-list"


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _repoint_url(node):
    return reverse("managed-nodes-repoint-meshtastic-id", kwargs={"internal_id": node.internal_id})


def _ack_url(event):
    return reverse("managed-node-identity-events-acknowledge", kwargs={"pk": event.pk})


def _event(node, outcome=Outcome.AUTO_UPDATED, reason=None, **extra):
    return ManagedNodeIdentityEvent.objects.create(
        managed_node=node,
        old_meshtastic_node_id=OLD_NUM,
        new_meshtastic_node_id=NEW_NUM,
        reported_public_key=KEY_HEX,
        outcome=outcome,
        reason=reason,
        **extra,
    )


@pytest.fixture
def owner(create_user):
    return create_user()


@pytest.fixture
def feeder(create_managed_node, owner):
    return create_managed_node(
        owner=owner,
        meshtastic_node_id=OLD_NUM,
        name="Hill",
        reported_meshtastic_node_id=NEW_NUM,
        meshtastic_public_key=KEY_HEX,
    )


@pytest.fixture
def staff(create_user):
    return create_user(is_staff=True)


def _forget_key(node):
    node.meshtastic_public_key = None
    node.save(update_fields=["meshtastic_public_key"])


@pytest.fixture
def received():
    calls = []

    def handler(sender, **kwargs):
        calls.append(kwargs)

    feeder_identity_changed.connect(handler)
    yield calls
    feeder_identity_changed.disconnect(handler)


# --- re-point ---------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_repoint_defaults_to_reported_number(feeder, owner, received):
    response = _client(owner).post(_repoint_url(feeder), {}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["outcome"] == "manual"
    assert response.data["old_meshtastic_node_id"] == OLD_NUM
    assert response.data["new_meshtastic_node_id"] == NEW_NUM
    assert response.data["old_node_id_str"] == "!da545c78"
    assert response.data["new_node_id_str"] == "!4396524c"
    assert response.data["managed_node"] == str(feeder.internal_id)
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == NEW_NUM
    assert len(received) == 1
    assert received[0]["event"].outcome == Outcome.MANUAL
    assert (received[0]["old_node_id"], received[0]["new_node_id"]) == (OLD_NUM, NEW_NUM)


@pytest.mark.django_db
def test_repoint_creates_missing_observed_node_unclaimed(feeder, owner):
    _client(owner).post(_repoint_url(feeder), {}, format="json")
    observed = ObservedNode.objects.get(protocol=Protocol.MESHTASTIC, meshtastic_node_id=NEW_NUM)
    assert observed.claimed_by_id is None


@pytest.mark.django_db
def test_owner_repoint_leaves_existing_observed_node_unclaimed(feeder, owner, create_observed_node):
    target = create_observed_node(meshtastic_node_id=NEW_NUM, claimed_by=None)
    assert _client(owner).post(_repoint_url(feeder), {}, format="json").status_code == 200
    target.refresh_from_db()
    assert target.claimed_by_id is None


@pytest.mark.django_db
def test_staff_repoint_leaves_existing_observed_node_unclaimed(feeder, staff, create_observed_node):
    target = create_observed_node(meshtastic_node_id=0x0BADF00D, claimed_by=None)
    response = _client(staff).post(_repoint_url(feeder), {"meshtastic_node_id": 0x0BADF00D}, format="json")
    assert response.status_code == 200, response.data
    target.refresh_from_db()
    assert target.claimed_by_id is None


@pytest.mark.django_db
def test_owner_cannot_repoint_to_an_unreported_number(feeder, owner, create_observed_node):
    victim = create_observed_node(meshtastic_node_id=0x0BADF00D, claimed_by=None)
    response = _client(owner).post(_repoint_url(feeder), {"meshtastic_node_id": 0x0BADF00D}, format="json")
    assert response.status_code == 403
    assert response.data["code"] == "repoint_not_proven"
    feeder.refresh_from_db()
    victim.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM
    assert victim.claimed_by_id is None
    assert not feeder.identity_events.exists()


@pytest.mark.django_db
def test_owner_cannot_repoint_to_a_proven_number_the_feeder_did_not_report(feeder, owner):
    feeder.reported_meshtastic_node_id = 0x12345678
    feeder.save(update_fields=["reported_meshtastic_node_id"])
    response = _client(owner).post(_repoint_url(feeder), {"meshtastic_node_id": NEW_NUM}, format="json")
    assert response.status_code == 403
    assert response.data["code"] == "repoint_not_proven"


@pytest.mark.django_db
def test_owner_repoint_needs_a_stored_key(feeder, owner):
    _forget_key(feeder)
    response = _client(owner).post(_repoint_url(feeder), {}, format="json")
    assert response.status_code == 403
    assert response.data["code"] == "repoint_not_proven"


@pytest.mark.django_db
def test_owner_repoint_needs_the_key_to_give_the_number(feeder, owner):
    feeder.meshtastic_public_key = OTHER_KEY_HEX
    feeder.save(update_fields=["meshtastic_public_key"])
    response = _client(owner).post(_repoint_url(feeder), {}, format="json")
    assert response.status_code == 403
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_owner_repoint_refuses_a_key_recorded_just_now(feeder, owner):
    _event(feeder, Outcome.KEY_CHANGED)
    response = _client(owner).post(_repoint_url(feeder), {}, format="json")
    assert response.status_code == 403
    assert response.data["code"] == "repoint_not_proven"


@pytest.mark.django_db
def test_owner_repoint_keeps_the_stored_key_over_a_flagged_report(feeder, owner):
    ManagedNodeIdentityEvent.objects.create(
        managed_node=feeder,
        old_meshtastic_node_id=OLD_NUM,
        new_meshtastic_node_id=NEW_NUM,
        reported_public_key=OTHER_KEY_HEX,
        outcome=Outcome.FLAGGED,
        reason=Reason.CRC_MISMATCH,
    )
    assert _client(owner).post(_repoint_url(feeder), {}, format="json").status_code == 200
    feeder.refresh_from_db()
    assert feeder.meshtastic_public_key == KEY_HEX
    assert ManagedNodeIdentityEvent.objects.get(outcome=Outcome.MANUAL).reported_public_key == KEY_HEX


@pytest.mark.django_db
def test_staff_repoint_explicit_number(feeder, staff):
    response = _client(staff).post(_repoint_url(feeder), {"meshtastic_node_id": 0x12345678}, format="json")
    assert response.status_code == 200, response.data
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == 0x12345678


@pytest.mark.django_db
def test_staff_repoint_takes_key_from_open_flagged_event(feeder, staff):
    _forget_key(feeder)
    flagged = _event(feeder, Outcome.FLAGGED, Reason.AUTO_REKEY_DISABLED)
    response = _client(staff).post(_repoint_url(feeder), {}, format="json")
    assert response.status_code == 200, response.data
    feeder.refresh_from_db()
    assert feeder.meshtastic_public_key == KEY_HEX
    assert feeder.meshtastic_key_node_id == key_node_id(KEY_HEX) == NEW_NUM
    flagged.refresh_from_db()
    assert flagged.resolved_at is not None
    assert flagged.acknowledged_by == staff
    manual = ManagedNodeIdentityEvent.objects.get(outcome=Outcome.MANUAL)
    assert manual.reported_public_key == KEY_HEX
    assert manual.acknowledged_at is not None


@pytest.mark.django_db
def test_staff_repoint_ignores_flagged_event_for_another_number(feeder, staff):
    _forget_key(feeder)
    _event(feeder, Outcome.FLAGGED, Reason.AUTO_REKEY_DISABLED)
    response = _client(staff).post(_repoint_url(feeder), {"meshtastic_node_id": 0x12345678}, format="json")
    assert response.status_code == 200
    feeder.refresh_from_db()
    assert feeder.meshtastic_public_key is None


@pytest.mark.django_db
def test_repoint_works_with_auto_rekey_off(feeder, owner, settings):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = False
    assert _client(owner).post(_repoint_url(feeder), {}, format="json").status_code == 200


@pytest.mark.django_db
def test_staff_can_reverse_a_rekey(feeder, owner, staff):
    assert _client(owner).post(_repoint_url(feeder), {}, format="json").status_code == 200
    assert _client(owner).post(_repoint_url(feeder), {"meshtastic_node_id": OLD_NUM}, format="json").status_code == 403
    response = _client(staff).post(_repoint_url(feeder), {"meshtastic_node_id": OLD_NUM}, format="json")
    assert response.status_code == 200, response.data
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM
    manual = list(feeder.identity_events.filter(outcome=Outcome.MANUAL).order_by("id"))
    assert [(e.old_meshtastic_node_id, e.new_meshtastic_node_id) for e in manual] == [
        (OLD_NUM, NEW_NUM),
        (NEW_NUM, OLD_NUM),
    ]


def _reverse_by_staff(feeder, staff):
    client = _client(staff)
    assert client.post(_repoint_url(feeder), {"meshtastic_node_id": NEW_NUM}, format="json").status_code == 200
    assert client.post(_repoint_url(feeder), {"meshtastic_node_id": OLD_NUM}, format="json").status_code == 200
    feeder.refresh_from_db()


@pytest.mark.django_db
def test_reversal_holds_while_radio_reports_the_reversed_number(feeder, staff, settings):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    _reverse_by_staff(feeder, staff)
    event = apply_reported_identity(feeder, reported_node_num=NEW_NUM, reported_pubkey=KEY_HEX)
    assert (event.outcome, event.reason) == (Outcome.FLAGGED, Reason.AUTO_REKEY_DISABLED)
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM
    assert apply_reported_identity(feeder, reported_node_num=NEW_NUM, reported_pubkey=KEY_HEX) is None


@pytest.mark.django_db
def test_owner_can_accept_a_held_number_by_hand(feeder, owner, staff, settings):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    _reverse_by_staff(feeder, staff)
    assert _client(owner).post(_repoint_url(feeder), {}, format="json").status_code == 200
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == NEW_NUM


@pytest.mark.django_db
def test_later_manual_repoint_lifts_the_hold(feeder, staff, settings):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    _reverse_by_staff(feeder, staff)
    response = _client(staff).post(_repoint_url(feeder), {"meshtastic_node_id": 0x12345678}, format="json")
    assert response.status_code == 200
    feeder.refresh_from_db()
    event = apply_reported_identity(feeder, reported_node_num=NEW_NUM, reported_pubkey=KEY_HEX)
    assert (event.outcome, event.reason) == (Outcome.AUTO_UPDATED, None)
    assert feeder.meshtastic_node_id == NEW_NUM


@pytest.mark.django_db
def test_repoint_resolves_all_open_flagged_rows(feeder, owner):
    a = _event(feeder, Outcome.FLAGGED, Reason.KEY_NOT_REPORTED)
    b = _event(feeder, Outcome.FLAGGED, Reason.AUTO_REKEY_DISABLED)
    _client(owner).post(_repoint_url(feeder), {}, format="json")
    for row in (a, b):
        row.refresh_from_db()
        assert row.resolved_at is not None


@pytest.mark.django_db
def test_repoint_forbidden_for_other_user(feeder, create_user):
    response = _client(create_user()).post(_repoint_url(feeder), {}, format="json")
    assert response.status_code == 403
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_repoint_allowed_for_staff(feeder, create_user):
    staff = create_user(is_staff=True)
    assert _client(staff).post(_repoint_url(feeder), {}, format="json").status_code == 200


@pytest.mark.django_db
def test_repoint_requires_authentication(feeder):
    assert APIClient().post(_repoint_url(feeder), {}, format="json").status_code in (401, 403)


@pytest.mark.django_db
def test_repoint_collision_is_409(feeder, owner, create_managed_node):
    create_managed_node(meshtastic_node_id=NEW_NUM, name="Other")
    response = _client(owner).post(_repoint_url(feeder), {}, format="json")
    assert response.status_code == 409
    assert response.data["code"] == "number_collision"
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM
    assert not ManagedNodeIdentityEvent.objects.exists()


@pytest.mark.django_db
def test_repoint_non_object_body_is_400(feeder, owner):
    response = _client(owner).post(_repoint_url(feeder), [1, 2], format="json")
    assert response.status_code == 400
    assert response.data["code"] == "invalid_node_id"
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


def _detail_url(node):
    return reverse("managed-nodes-detail", kwargs={"internal_id": node.internal_id})


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["patch", "put"])
def test_owner_update_cannot_change_the_number(feeder, owner, method):
    body = {"meshtastic_node_id": NEW_NUM, "name": "Renamed", "constellation_id": feeder.constellation_id}

    response = getattr(_client(owner), method)(_detail_url(feeder), body, format="json")

    assert response.status_code == 200
    feeder.refresh_from_db()
    assert (feeder.meshtastic_node_id, feeder.name) == (OLD_NUM, "Renamed")
    assert not feeder.identity_events.exists()


@pytest.mark.django_db
def test_owner_update_to_an_active_feeders_number_is_ignored(feeder, owner, create_managed_node):
    create_managed_node(meshtastic_node_id=NEW_NUM, name="Taken")

    response = _client(owner).patch(_detail_url(feeder), {"meshtastic_node_id": NEW_NUM}, format="json")

    assert response.status_code == 200
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["patch", "put"])
def test_staff_update_changes_the_number_through_the_audited_path(feeder, staff, received, method):
    flagged = _event(feeder, outcome=Outcome.FLAGGED, reason=Reason.AUTO_REKEY_DISABLED)
    body = {"meshtastic_node_id": NEW_NUM, "name": "Renamed", "constellation_id": feeder.constellation_id}

    response = getattr(_client(staff), method)(_detail_url(feeder), body, format="json")

    assert response.status_code == 200, response.data
    feeder.refresh_from_db()
    assert (feeder.meshtastic_node_id, feeder.name) == (NEW_NUM, "Renamed")
    manual = feeder.identity_events.get(outcome=Outcome.MANUAL)
    assert (manual.old_meshtastic_node_id, manual.new_meshtastic_node_id) == (OLD_NUM, NEW_NUM)
    assert manual.acknowledged_by == staff
    flagged.refresh_from_db()
    assert flagged.resolved_at is not None
    assert ObservedNode.objects.filter(protocol=Protocol.MESHTASTIC, meshtastic_node_id=NEW_NUM).exists()
    assert len(received) == 1


@pytest.mark.django_db
def test_staff_update_with_the_same_number_writes_no_event(feeder, staff):
    response = _client(staff).patch(_detail_url(feeder), {"meshtastic_node_id": OLD_NUM, "name": "Same"}, format="json")

    assert response.status_code == 200
    assert not feeder.identity_events.exists()


@pytest.mark.django_db
def test_staff_update_to_an_active_feeders_number_is_409_and_changes_nothing(feeder, staff, create_managed_node):
    create_managed_node(meshtastic_node_id=NEW_NUM, name="Taken")

    response = _client(staff).patch(_detail_url(feeder), {"meshtastic_node_id": NEW_NUM, "name": "X"}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "number_collision"
    feeder.refresh_from_db()
    assert (feeder.meshtastic_node_id, feeder.name) == (OLD_NUM, "Hill")
    assert not feeder.identity_events.exists()


@pytest.mark.django_db
def test_staff_update_constraint_race_is_409_not_500(feeder, staff, create_managed_node):
    """The pre-check misses a feeder that took the number a moment ago: the unique index answers, not a 500."""
    create_managed_node(meshtastic_node_id=NEW_NUM, name="Taken")
    with patch("nodes.services.feeder_identity._number_held_by_another_feeder", return_value=False):
        response = _client(staff).patch(_detail_url(feeder), {"meshtastic_node_id": NEW_NUM}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "number_collision"
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_staff_update_with_an_invalid_number_is_400(feeder, staff):
    response = _client(staff).patch(_detail_url(feeder), {"meshtastic_node_id": 2}, format="json")

    assert response.status_code == 400
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


# --- staff accept a reported key for the unchanged number --------------------------------------------------------


def _key_regenerated(feeder):
    """The 2.7 case: the MAC-derived number stays, the owner regenerated the key, the feeder reports the new one."""
    ManagedNode.objects.filter(pk=feeder.pk).update(meshtastic_public_key=OTHER_KEY_HEX)
    feeder.refresh_from_db()
    return apply_reported_identity(feeder, reported_node_num=OLD_NUM, reported_pubkey=KEY_HEX)


@pytest.mark.django_db
def test_key_regeneration_sequence_end_to_end(feeder, staff, received):
    flagged = _key_regenerated(feeder)
    assert (flagged.outcome, flagged.reason) == (Outcome.FLAGGED, Reason.KEY_MISMATCH)

    response = _client(staff).post(_repoint_url(feeder), {"accept_reported_key": True}, format="json")

    assert response.status_code == 200, response.data
    assert response.data["outcome"] == "key_accepted"
    assert response.data["old_meshtastic_node_id"] == response.data["new_meshtastic_node_id"] == OLD_NUM
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM
    assert feeder.meshtastic_public_key == KEY_HEX
    assert feeder.meshtastic_key_node_id == key_node_id(KEY_HEX)
    flagged.refresh_from_db()
    assert flagged.resolved_at is not None and flagged.acknowledged_by == staff
    audit = feeder.identity_events.get(outcome=Outcome.KEY_ACCEPTED)
    assert audit.reported_public_key == KEY_HEX and audit.acknowledged_by == staff
    assert not received

    before = feeder.identity_events.count()
    assert apply_reported_identity(feeder, reported_node_num=OLD_NUM, reported_pubkey=KEY_HEX) is None
    assert feeder.identity_events.count() == before


@pytest.mark.django_db
def test_owner_cannot_accept_a_reported_key(feeder, owner):
    _key_regenerated(feeder)

    response = _client(owner).post(_repoint_url(feeder), {"accept_reported_key": True}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "staff_only"
    feeder.refresh_from_db()
    assert feeder.meshtastic_public_key == OTHER_KEY_HEX


@pytest.mark.django_db
def test_accept_without_a_waiting_key_is_400(feeder, staff):
    response = _client(staff).post(_repoint_url(feeder), {"accept_reported_key": True}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "no_key_to_accept"


@pytest.mark.django_db
def test_accept_ignores_a_flagged_row_for_another_reason(feeder, staff):
    _event(feeder, outcome=Outcome.FLAGGED, reason=Reason.AUTO_REKEY_DISABLED)

    response = _client(staff).post(_repoint_url(feeder), {"accept_reported_key": True}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "no_key_to_accept"


@pytest.mark.django_db
def test_accept_with_another_number_is_400(feeder, staff):
    _key_regenerated(feeder)
    body = {"accept_reported_key": True, "meshtastic_node_id": NEW_NUM}

    response = _client(staff).post(_repoint_url(feeder), body, format="json")

    assert response.status_code == 400
    feeder.refresh_from_db()
    assert feeder.meshtastic_public_key == OTHER_KEY_HEX and feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_accept_flag_must_be_a_boolean(feeder, staff):
    response = _client(staff).post(_repoint_url(feeder), {"accept_reported_key": "yes"}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "invalid_accept_reported_key"


@pytest.mark.django_db
def test_accepted_key_is_trusted_at_once_for_the_auto_rekey(feeder, staff, settings):
    settings.MESHTASTIC_FEEDER_AUTO_REKEY = True
    _key_regenerated(feeder)
    _client(staff).post(_repoint_url(feeder), {"accept_reported_key": True}, format="json")
    feeder.refresh_from_db()

    event = apply_reported_identity(feeder, reported_node_num=NEW_NUM, reported_pubkey=KEY_HEX)

    assert (event.outcome, event.reason) == (Outcome.AUTO_UPDATED, None)


# --- a receiver that raises -------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_raising_receiver_leaves_the_repoint_applied_and_the_response_200(feeder, owner):
    def broken(sender, **kwargs):
        raise RuntimeError("boom")

    feeder_identity_changed.connect(broken)
    try:
        response = _client(owner).post(_repoint_url(feeder), {}, format="json")
    finally:
        feeder_identity_changed.disconnect(broken)

    assert response.status_code == 200, response.data
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == NEW_NUM
    assert feeder.identity_events.filter(outcome=Outcome.MANUAL).exists()


@pytest.mark.django_db
def test_failing_ensure_leaves_the_repoint_applied_and_the_response_200(feeder, owner, received):
    with patch("nodes.services.feeder_identity.ensure_observed_node_for_managed_node", side_effect=RuntimeError("x")):
        response = _client(owner).post(_repoint_url(feeder), {}, format="json")

    assert response.status_code == 200, response.data
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == NEW_NUM
    assert len(received) == 1


@pytest.mark.django_db
def test_owner_repoint_refuses_a_target_claimed_by_someone_else(feeder, owner, create_observed_node, create_user):
    target = create_observed_node(
        meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=KEY_HEX, claimed_by=create_user()
    )

    response = _client(owner).post(_repoint_url(feeder), {}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "repoint_target_claimed"
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM
    target.refresh_from_db()
    assert target.claimed_by_id != owner.pk


@pytest.mark.django_db
def test_owner_repoint_refuses_a_target_with_a_different_key(feeder, owner, create_observed_node):
    create_observed_node(meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=OTHER_KEY_HEX, claimed_by=None)

    response = _client(owner).post(_repoint_url(feeder), {}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "repoint_target_key_mismatch"
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM


@pytest.mark.django_db
def test_owner_repoint_without_proof_gets_not_proven_before_target_checks(feeder, owner, create_observed_node):
    _forget_key(feeder)
    create_observed_node(meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=OTHER_KEY_HEX, claimed_by=None)

    response = _client(owner).post(_repoint_url(feeder), {}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "repoint_not_proven"


@pytest.mark.django_db
def test_owner_repoint_to_their_own_claimed_target(feeder, owner, create_observed_node):
    create_observed_node(meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=KEY_HEX, claimed_by=owner)

    assert _client(owner).post(_repoint_url(feeder), {}, format="json").status_code == 200


@pytest.mark.django_db
def test_staff_repoint_is_exempt_from_target_checks(feeder, staff, create_observed_node, create_user):
    create_observed_node(meshtastic_node_id=NEW_NUM, meshtastic_public_key_hex=OTHER_KEY_HEX, claimed_by=create_user())

    assert _client(staff).post(_repoint_url(feeder), {}, format="json").status_code == 200


@pytest.mark.django_db
def test_repoint_constraint_race_is_409(feeder, owner, create_managed_node):
    create_managed_node(meshtastic_node_id=NEW_NUM, name="Other")
    with patch("nodes.services.feeder_identity._number_held_by_another_feeder", return_value=False):
        response = _client(owner).post(_repoint_url(feeder), {}, format="json")
    assert response.status_code == 409
    assert response.data["code"] == "number_collision"
    feeder.refresh_from_db()
    assert feeder.meshtastic_node_id == OLD_NUM
    assert not feeder.identity_events.exists()


@pytest.mark.django_db
def test_repoint_already_current_is_400(feeder, owner):
    response = _client(owner).post(_repoint_url(feeder), {"meshtastic_node_id": OLD_NUM}, format="json")
    assert response.status_code == 400
    assert response.data["code"] == "already_current"


@pytest.mark.django_db
def test_repoint_meshcore_node_is_400(create_user, create_managed_node):
    user = create_user()
    node = create_managed_node(owner=user, meshtastic_node_id=0, protocol=Protocol.MESHCORE)
    response = _client(user).post(_repoint_url(node), {"meshtastic_node_id": NEW_NUM}, format="json")
    assert response.status_code == 400
    assert response.data["code"] == "not_meshtastic"


@pytest.mark.django_db
def test_repoint_without_reported_number_is_400(create_managed_node, owner):
    node = create_managed_node(owner=owner, meshtastic_node_id=OLD_NUM, reported_meshtastic_node_id=None)
    response = _client(owner).post(_repoint_url(node), {}, format="json")
    assert response.status_code == 400
    assert response.data["code"] == "no_reported_number"


@pytest.mark.django_db
@pytest.mark.parametrize("value", ["!4396524c", "12", 1.5, True, -5, 0, 0xFFFFFFFF, 2**40])
def test_repoint_invalid_number_is_400(feeder, owner, value):
    response = _client(owner).post(_repoint_url(feeder), {"meshtastic_node_id": value}, format="json")
    assert response.status_code == 400
    assert response.data["code"] == "invalid_node_id"


# --- list -------------------------------------------------------------------------------------------------------


def _results(response):
    assert response.status_code == 200, response.data
    return response.data["results"]


@pytest.mark.django_db
def test_list_shape_and_pagination(feeder, owner):
    event = _event(feeder, Outcome.FLAGGED, Reason.NUMBER_COLLISION)
    response = _client(owner).get(reverse(LIST_URL))
    assert response.data["count"] == 1
    assert dict(_results(response)[0]) == {
        "id": event.pk,
        "managed_node": str(feeder.internal_id),
        "managed_node_name": "Hill",
        "old_meshtastic_node_id": OLD_NUM,
        "old_node_id_str": "!da545c78",
        "new_meshtastic_node_id": NEW_NUM,
        "new_node_id_str": "!4396524c",
        "outcome": "flagged",
        "reason": "number_collision",
        "needs_action": True,
        "created_at": _results(response)[0]["created_at"],
        "resolved_at": None,
        "acknowledged_at": None,
    }


@pytest.mark.django_db
def test_list_owner_sees_only_own_feeders(feeder, owner, create_managed_node):
    other = create_managed_node(meshtastic_node_id=0x11111111)
    mine = _event(feeder)
    _event(other)
    ids = [row["id"] for row in _results(_client(owner).get(reverse(LIST_URL)))]
    assert ids == [mine.pk]


@pytest.mark.django_db
def test_list_staff_sees_all(feeder, create_managed_node, create_user):
    other = create_managed_node(meshtastic_node_id=0x11111111)
    _event(feeder)
    _event(other)
    rows = _results(_client(create_user(is_staff=True)).get(reverse(LIST_URL)))
    assert len(rows) == 2


@pytest.mark.django_db
def test_list_unacknowledged_drops_acknowledged_and_key_changed(feeder, owner):
    open_row = _event(feeder, Outcome.FLAGGED, Reason.KEY_MISMATCH)
    _event(feeder, acknowledged_at=timezone.now(), acknowledged_by=owner)
    _event(feeder, Outcome.KEY_CHANGED)
    client = _client(owner)
    assert len(_results(client.get(reverse(LIST_URL)))) == 3
    rows = _results(client.get(reverse(LIST_URL), {"unacknowledged": "true"}))
    assert [row["id"] for row in rows] == [open_row.pk]


@pytest.mark.django_db
def test_list_filters_by_managed_node(feeder, owner, create_managed_node):
    second = create_managed_node(owner=owner, meshtastic_node_id=0x22222222)
    _event(feeder)
    wanted = _event(second)
    client = _client(owner)
    rows = _results(client.get(reverse(LIST_URL), {"managed_node": str(second.internal_id)}))
    assert [row["id"] for row in rows] == [wanted.pk]
    assert _results(client.get(reverse(LIST_URL), {"managed_node": "not-a-uuid"})) == []


@pytest.mark.django_db
def test_needs_action_flags(feeder, owner):
    now = timezone.now()
    open_flagged = _event(feeder, Outcome.FLAGGED, Reason.CRC_MISMATCH)
    resolved_flagged = _event(feeder, Outcome.FLAGGED, Reason.CRC_MISMATCH, resolved_at=now)
    auto = _event(feeder, Outcome.AUTO_UPDATED)
    by_id = {row["id"]: row["needs_action"] for row in _results(_client(owner).get(reverse(LIST_URL)))}
    assert by_id == {open_flagged.pk: True, resolved_flagged.pk: False, auto.pk: False}


@pytest.mark.django_db
def test_list_query_count_does_not_grow_with_events(feeder, owner, django_assert_num_queries):
    client = _client(owner)
    _event(feeder)
    with CaptureQueriesContext(connection) as one:
        assert len(_results(client.get(reverse(LIST_URL)))) == 1
    for _ in range(4):
        _event(feeder)
    with django_assert_num_queries(len(one)):
        assert len(_results(client.get(reverse(LIST_URL)))) == 5


@pytest.mark.django_db
def test_list_orders_newest_first(feeder, owner):
    old = _event(feeder)
    ManagedNodeIdentityEvent.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))
    new = _event(feeder)
    ids = [row["id"] for row in _results(_client(owner).get(reverse(LIST_URL)))]
    assert ids == [new.pk, old.pk]


@pytest.mark.django_db
def test_list_requires_authentication():
    assert APIClient().get(reverse(LIST_URL)).status_code in (401, 403)


@pytest.mark.django_db
def test_managed_nodes_mine_still_routes(feeder, owner):
    response = _client(owner).get("/api/nodes/managed-nodes/mine/")
    assert response.status_code == 200
    assert response.data["count"] == 1


# --- acknowledge ------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_acknowledge_records_user_and_time(feeder, owner):
    event = _event(feeder, Outcome.FLAGGED, Reason.KEY_MISMATCH)
    response = _client(owner).post(_ack_url(event))
    assert response.status_code == 200
    assert response.data["acknowledged_at"] is not None
    event.refresh_from_db()
    assert event.acknowledged_by == owner
    assert event.acknowledged_at is not None


@pytest.mark.django_db
def test_acknowledge_is_idempotent(feeder, owner, create_user):
    event = _event(feeder)
    client = _client(owner)
    client.post(_ack_url(event))
    event.refresh_from_db()
    first = (event.acknowledged_at, event.acknowledged_by_id)
    staff = create_user(is_staff=True)
    assert _client(staff).post(_ack_url(event)).status_code == 200
    assert client.post(_ack_url(event)).status_code == 200
    event.refresh_from_db()
    assert (event.acknowledged_at, event.acknowledged_by_id) == first


@pytest.mark.django_db
def test_acknowledge_other_users_event_is_404(feeder, create_user):
    event = _event(feeder)
    response = _client(create_user()).post(_ack_url(event))
    assert response.status_code == 404
    event.refresh_from_db()
    assert event.acknowledged_at is None
