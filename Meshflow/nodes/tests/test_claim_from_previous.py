"""One-tap claim of a node's new number: ``POST observed-nodes/{id}/claim-from-previous/``."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.db import connection
from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.meshtastic_identity import identity_fields, normalise_pubkey
from nodes.models import NodeOwnerClaim, ObservedNodeIdentityLink
from nodes.services import identity_links
from nodes.services.identity_links import IdentityLinkError, detect_after_key_write

Link = ObservedNodeIdentityLink
State = Link.State
Evidence = Link.Evidence
NEW_ROW = {"trigger": "new_row"}


@pytest.fixture
def owner(create_user):
    return create_user()


@pytest.fixture
def make_pair(create_observed_node):
    def make(
        owner,
        state=State.AUTO,
        evidence=Evidence.PUBLIC_KEY,
        new_owner=None,
        old_owner="owner",
        detail=NEW_ROW,
        reviewer=None,
        base=0x62000001,
    ):
        old = create_observed_node(meshtastic_node_id=base, claimed_by=owner if old_owner == "owner" else old_owner)
        new = create_observed_node(meshtastic_node_id=base + 1, claimed_by=new_owner)
        link = Link.objects.create(
            old_node=old,
            new_node=new,
            evidence=evidence,
            confidence=Link.Confidence.STRONG,
            state=state,
            detail=detail or {},
            reviewed_by=reviewer,
        )
        return old, new, link

    return make


def post(user, node, lookup=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    url = reverse("observed-node-claim-from-previous", kwargs={"internal_id": lookup or str(node.internal_id)})
    return client.post(url, {}, format="json")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state,evidence,detail,staff_reviewer",
    [
        (State.AUTO, Evidence.PUBLIC_KEY, NEW_ROW, False),
        (State.AUTO, Evidence.FEEDER_REKEY, None, False),
        (State.CONFIRMED, Evidence.DECLARED, None, False),
        (State.CONFIRMED, Evidence.MAC, None, True),
        (State.CONFIRMED, Evidence.PREDICTED_NUMBER, None, True),
    ],
)
def test_claims_new_node_on_strong_evidence(
    owner, make_pair, create_user, state, evidence, detail, staff_reviewer, django_capture_on_commit_callbacks
):
    reviewer = create_user(is_staff=True) if staff_reviewer else None
    old, new, _ = make_pair(owner, state=state, evidence=evidence, detail=detail, reviewer=reviewer)
    with patch("nodes.ws_notify.notify_node_claim_accepted") as notify:
        with django_capture_on_commit_callbacks(execute=True):
            response = post(owner, new)
    assert response.status_code == 201
    new.refresh_from_db()
    old.refresh_from_db()
    assert new.claimed_by_id == owner.pk
    assert old.claimed_by_id == owner.pk  # the old claim is left alone
    claim = NodeOwnerClaim.objects.get(node=new, user=owner)
    assert claim.accepted_at is not None and claim.claim_key
    assert response.data["node"]["node_id_str"] == new.node_id_str
    notify.assert_called_once()
    assert notify.call_args.kwargs["claim"].pk == claim.pk


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state,evidence,detail",
    [
        (State.AUTO, Evidence.PREDICTED_NUMBER, None),
        (State.AUTO, Evidence.MAC, None),
        (State.CONFIRMED, Evidence.MAC, None),  # owner-confirmed (set below)
        (State.CONFIRMED, Evidence.PREDICTED_NUMBER, None),  # owner-confirmed (set below)
        (State.AUTO, Evidence.PUBLIC_KEY, None),  # no trigger recorded (every pre-existing link)
        (State.AUTO, Evidence.PUBLIC_KEY, {"trigger": "old_row"}),
        (State.CONFIRMED, Evidence.PUBLIC_KEY, {"trigger": "old_row"}),  # owner-confirmed, old row triggered
    ],
)
def test_weak_evidence_is_refused(owner, make_pair, state, evidence, detail):
    reviewer = owner if state == State.CONFIRMED else None  # an owner's own confirm never counts
    _, new, _ = make_pair(owner, state=state, evidence=evidence, detail=detail, reviewer=reviewer)
    response = post(owner, new)
    assert response.status_code == 409
    assert response.data["code"] == "evidence_too_weak"
    assert "proving the radio" in response.data["detail"]
    new.refresh_from_db()
    assert new.claimed_by_id is None
    assert not NodeOwnerClaim.objects.filter(node=new).exists()


@pytest.mark.django_db
def test_confirm_by_a_non_staff_user_never_counts(owner, make_pair, create_user):
    _, new, _ = make_pair(owner, state=State.CONFIRMED, evidence=Evidence.MAC, reviewer=create_user())
    assert post(owner, new).data["code"] == "evidence_too_weak"


@pytest.mark.django_db
def test_owner_confirms_a_spoofed_mac_link_through_the_api_and_still_cannot_claim(owner, create_observed_node):
    """The verifier's route: confirm your own weak suggested link, then tap."""
    old = create_observed_node(meshtastic_node_id=0x62000001, claimed_by=owner)
    new = create_observed_node(meshtastic_node_id=0x62000002)
    link = Link.objects.create(
        old_node=old, new_node=new, evidence=Evidence.MAC, confidence=Link.Confidence.MEDIUM, state=State.SUGGESTED
    )
    client = APIClient()
    client.force_authenticate(user=owner)
    confirmed = client.post(reverse("identity-links-confirm", kwargs={"pk": link.pk}))
    assert confirmed.status_code == 200
    response = post(owner, new)
    assert (response.status_code, response.data["code"]) == (409, "evidence_too_weak")


# --- key links: which side appeared decides --------------------------------------------------------------------

KEY = "11" * 32


@pytest.fixture
def key_row(create_observed_node):
    def make(number, claimed_by=None):
        return create_observed_node(
            meshtastic_node_id=number,
            claimed_by=claimed_by,
            mac_addr=None,
            meshtastic_public_key=normalise_pubkey(KEY),
            **identity_fields(KEY),
        )

    return make


@pytest.mark.django_db
def test_genuine_upgrade_new_row_appears_with_the_old_rows_key(owner, key_row):
    from common.meshtastic_identity import key_node_id

    old = key_row(0x62000001, claimed_by=owner)
    new = key_row(key_node_id(KEY))
    assert detect_after_key_write(new) == identity_links.Outcome.CREATED
    assert Link.objects.get().detail["trigger"] == "new_row"
    assert post(owner, new).status_code == 201
    assert old.pk != new.pk


@pytest.mark.django_db
def test_two_holder_spoof_old_row_announces_the_victims_key(create_user, create_observed_node, key_row):
    """The attacker's old row announces a key the victim's (unclaimed) new row holds: no one-tap claim."""
    from common.meshtastic_identity import key_node_id

    attacker = create_user()
    victim_new = key_row(key_node_id(KEY))
    attacker_old = key_row(0x62000001, claimed_by=attacker)
    assert detect_after_key_write(attacker_old) == identity_links.Outcome.CREATED
    assert Link.objects.get().detail["trigger"] == "old_row"
    response = post(attacker, victim_new)
    assert (response.status_code, response.data["code"]) == (409, "evidence_too_weak")
    victim_new.refresh_from_db()
    assert victim_new.claimed_by_id is None


@pytest.mark.django_db
def test_backfill_records_no_trigger(owner, key_row):
    from common.meshtastic_identity import key_node_id

    key_row(0x62000001, claimed_by=owner)
    new = key_row(key_node_id(KEY))
    identity_links.evaluate_key(KEY)
    assert "trigger" not in Link.objects.get().detail
    assert post(owner, new).data["code"] == "evidence_too_weak"


@pytest.mark.django_db
@pytest.mark.parametrize("state", [State.SUGGESTED, State.REJECTED])
def test_a_link_that_is_not_live_is_no_previous(owner, make_pair, state):
    _, new, _ = make_pair(owner, state=state, evidence=Evidence.PUBLIC_KEY, detail=NEW_ROW)
    response = post(owner, new)
    assert response.status_code == 404
    assert response.data["code"] == "no_previous"


@pytest.mark.django_db
def test_no_link_at_all_is_no_previous(owner, create_observed_node):
    node = create_observed_node(meshtastic_node_id=0x62000009)
    response = post(owner, node)
    assert response.status_code == 404
    assert response.data["code"] == "no_previous"


@pytest.mark.django_db
def test_not_owner_of_old_row(owner, make_pair, create_user):
    _, new, _ = make_pair(owner)
    for user in (create_user(), create_user(is_staff=True)):
        response = post(user, new)
        assert response.status_code == 403
        assert response.data["code"] == "not_owner"
    new.refresh_from_db()
    assert new.claimed_by_id is None


@pytest.mark.django_db
def test_unclaimed_old_row_is_not_owner(owner, make_pair):
    _, new, _ = make_pair(owner, old_owner=None)
    assert post(owner, new).data["code"] == "not_owner"


@pytest.mark.django_db
def test_already_claimed_by_someone_else(owner, make_pair, create_user):
    other = create_user()
    _, new, _ = make_pair(owner, new_owner=other)
    response = post(owner, new)
    assert response.status_code == 409
    assert response.data["code"] == "already_claimed"
    new.refresh_from_db()
    assert new.claimed_by_id == other.pk


@pytest.mark.django_db
def test_already_mine_is_idempotent(owner, make_pair):
    _, new, _ = make_pair(owner)
    first = post(owner, new)
    second = post(owner, new)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.data == first.data
    assert NodeOwnerClaim.objects.filter(node=new, user=owner).count() == 1


@pytest.mark.django_db
def test_pending_claim_is_accepted_not_duplicated(owner, make_pair):
    _, new, _ = make_pair(owner)
    pending = NodeOwnerClaim.objects.create(node=new, user=owner, claim_key="a b 11")
    assert post(owner, new).status_code == 201
    pending.refresh_from_db()
    assert pending.accepted_at is not None
    assert NodeOwnerClaim.objects.filter(node=new, user=owner).count() == 1


@pytest.mark.django_db
def test_guest_is_refused(owner, make_pair):
    _, new, _ = make_pair(owner)
    assert post(None, new).status_code in (401, 403)


@pytest.mark.django_db
def test_lookup_by_hex_id(owner, make_pair):
    _, new, _ = make_pair(owner)
    assert post(owner, new, lookup=new.node_id_str).status_code == 201


@pytest.mark.django_db
def test_undo_is_the_existing_claim_delete(owner, make_pair):
    _, new, _ = make_pair(owner)
    post(owner, new)
    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("observed-node-claim", kwargs={"internal_id": new.internal_id})
    assert client.delete(url).status_code == 204
    new.refresh_from_db()
    assert new.claimed_by_id is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor == "sqlite", reason="needs row locks and concurrent connections")
def test_concurrent_taps_have_one_winner(owner, make_pair):
    """The new row is locked for the check and the write, so two taps make one claim."""
    _, new, _ = make_pair(owner, detail=NEW_ROW)

    def tap(_):
        try:
            return identity_links.claim_from_previous(new, owner)[1]
        except IdentityLinkError as exc:
            return exc.code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(tap, range(2)))
    assert sorted(map(str, results)) == ["False", "True"]
    assert NodeOwnerClaim.objects.filter(node=new, user=owner).count() == 1


@pytest.mark.django_db
def test_repeat_tap_by_the_holder_is_200_even_after_the_old_claim_is_gone(owner, make_pair):
    old, new, _ = make_pair(owner, detail=NEW_ROW)
    assert post(owner, new).status_code == 201
    old.claimed_by = None
    old.save(update_fields=["claimed_by"])
    response = post(owner, new)
    assert response.status_code == 200
    assert NodeOwnerClaim.objects.filter(node=new, user=owner).count() == 1


@pytest.mark.django_db
def test_no_notification_on_a_repeat_or_a_refusal(owner, make_pair, create_user, django_capture_on_commit_callbacks):
    _, new, _ = make_pair(owner, detail=NEW_ROW)
    _, weak_new, _ = make_pair(owner, evidence=Evidence.MAC, base=0x63000001)
    with patch("nodes.ws_notify.notify_node_claim_accepted") as notify:
        with django_capture_on_commit_callbacks(execute=True):
            assert post(owner, new).status_code == 201
        assert notify.call_count == 1
        with django_capture_on_commit_callbacks(execute=True):
            assert post(owner, new).status_code == 200  # repeat
            assert post(create_user(), new).status_code == 403  # not the owner
            assert post(owner, weak_new).status_code == 409  # refusal
        assert notify.call_count == 1


@pytest.mark.django_db
def test_new_claim_survives_deleting_the_old_claim(owner, make_pair):
    old, new, _ = make_pair(owner, detail=NEW_ROW)
    NodeOwnerClaim.objects.create(node=old, user=owner, claim_key="o l d 33", accepted_at=timezone.now())
    post(owner, new)
    client = APIClient()
    client.force_authenticate(user=owner)
    assert client.delete(reverse("observed-node-claim", kwargs={"internal_id": old.internal_id})).status_code == 204
    old.refresh_from_db()
    new.refresh_from_db()
    assert old.claimed_by_id is None
    assert new.claimed_by_id == owner.pk
    assert NodeOwnerClaim.objects.filter(node=new, user=owner, accepted_at__isnull=False).exists()


@pytest.mark.django_db
def test_another_users_pending_claim_is_left_in_place(owner, make_pair, create_user):
    """Proving the radio (the claim key sent from it) still wins later; the tap does not touch it."""
    other = create_user()
    _, new, _ = make_pair(owner, detail=NEW_ROW)
    theirs = NodeOwnerClaim.objects.create(node=new, user=other, claim_key="x y 22")
    assert post(owner, new).status_code == 201
    theirs.refresh_from_db()
    assert theirs.accepted_at is None
    assert NodeOwnerClaim.objects.filter(node=new).count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("lookup", ["!deadbeef", "00000000-0000-4000-8000-000000000000"])
def test_unknown_node_is_not_found_with_a_code(owner, lookup):
    client = APIClient()
    client.force_authenticate(user=owner)
    base = {"internal_id": lookup}
    for response in (
        client.post(reverse("observed-node-claim-from-previous", kwargs=base)),
        client.get(reverse("observed-node-identity-links", kwargs=base)),
        client.post(reverse("observed-node-identity-links", kwargs=base), {"new_node": "!00000001"}, format="json"),
    ):
        assert response.status_code == 404
        assert response.data["code"] == "not_found"
        assert response.data["detail"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor == "sqlite", reason="needs row locks and concurrent connections")
def test_two_users_tapping_at_once_one_wins(owner, create_observed_node, create_user):
    """Two different users reach the claim step together; only the row lock decides, so one gets already_claimed.

    A row has one owner, so the ownership test is patched to pass for both users: this exercises the lock.
    """
    rival = create_user()
    old = create_observed_node(meshtastic_node_id=0x62000001, claimed_by=owner)
    new = create_observed_node(meshtastic_node_id=0x62000002)
    Link.objects.create(
        old_node=old,
        new_node=new,
        evidence=Evidence.FEEDER_REKEY,
        confidence=Link.Confidence.STRONG,
        state=State.AUTO,
    )
    with patch.object(identity_links, "_owns", lambda user, node: True):

        def tap(user):
            try:
                return identity_links.claim_from_previous(new, user)[1]
            except IdentityLinkError as exc:
                return exc.code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(tap, [owner, rival]))
    assert sorted(map(str, results)) == ["True", "already_claimed"]
    new.refresh_from_db()
    assert new.claimed_by_id in (owner.pk, rival.pk)
    assert NodeOwnerClaim.objects.filter(node=new, accepted_at__isnull=False).count() == 1
