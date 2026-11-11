"""One-tap claim of a node's new number: ``POST observed-nodes/{id}/claim-from-previous/``."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.db import connection
from django.urls import reverse

import pytest
from rest_framework.test import APIClient

from nodes.models import NodeOwnerClaim, ObservedNodeIdentityLink
from nodes.services import identity_links
from nodes.services.identity_links import IdentityLinkError

Link = ObservedNodeIdentityLink
State = Link.State
Evidence = Link.Evidence


@pytest.fixture
def owner(create_user):
    return create_user()


@pytest.fixture
def make_pair(create_observed_node):
    def make(owner, state=State.AUTO, evidence=Evidence.PUBLIC_KEY, new_owner=None, old_owner="owner"):
        old = create_observed_node(
            meshtastic_node_id=0x62000001, claimed_by=owner if old_owner == "owner" else old_owner
        )
        new = create_observed_node(meshtastic_node_id=0x62000002, claimed_by=new_owner)
        link = Link.objects.create(
            old_node=old, new_node=new, evidence=evidence, confidence=Link.Confidence.STRONG, state=state
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
    "state,evidence",
    [
        (State.AUTO, Evidence.PUBLIC_KEY),
        (State.AUTO, Evidence.FEEDER_REKEY),
        (State.CONFIRMED, Evidence.PUBLIC_KEY),
        (State.CONFIRMED, Evidence.PREDICTED_NUMBER),
        (State.CONFIRMED, Evidence.MAC),
        (State.CONFIRMED, Evidence.DECLARED),
    ],
)
def test_claims_new_node_on_strong_evidence(owner, make_pair, state, evidence, django_capture_on_commit_callbacks):
    old, new, _ = make_pair(owner, state=state, evidence=evidence)
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
@pytest.mark.parametrize("evidence", [Evidence.PREDICTED_NUMBER, Evidence.MAC])
def test_weak_evidence_is_refused(owner, make_pair, evidence):
    _, new, _ = make_pair(owner, state=State.AUTO, evidence=evidence)
    response = post(owner, new)
    assert response.status_code == 409
    assert response.data["code"] == "evidence_too_weak"
    new.refresh_from_db()
    assert new.claimed_by_id is None
    assert not NodeOwnerClaim.objects.filter(node=new).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("state", [State.SUGGESTED, State.REJECTED])
def test_a_link_that_is_not_live_is_no_previous(owner, make_pair, state):
    _, new, _ = make_pair(owner, state=state, evidence=Evidence.PUBLIC_KEY)
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
    _, new, _ = make_pair(owner)

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
