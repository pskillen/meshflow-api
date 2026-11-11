"""Review of identity links by people: the service, its permission table and the endpoints (brief 158, part A)."""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol
from nodes.models import ObservedNode, ObservedNodeIdentityLink
from nodes.services import identity_links
from nodes.services.identity_links import IdentityLinkError
from nodes.signals import identity_link_live

Link = ObservedNodeIdentityLink
State = Link.State
Evidence = Link.Evidence

OLD, NEW, OTHER = 0x61000001, 0x61000002, 0x61000003


@pytest.fixture
def users(create_user):
    return {
        "anon": None,
        "stranger": create_user(),
        "owner_old": create_user(),
        "owner_new": create_user(),
        "owner_both": create_user(),
        "staff": create_user(is_staff=True),
    }


@pytest.fixture
def make_link(create_observed_node):
    def make(state=State.SUGGESTED, evidence=Evidence.MAC, old_owner=None, new_owner=None, old_n=OLD, new_n=NEW):
        old = create_observed_node(meshtastic_node_id=old_n, claimed_by=old_owner, long_name="Old", short_name="OLD")
        new = create_observed_node(meshtastic_node_id=new_n, claimed_by=new_owner, long_name="New", short_name="NEW")
        return Link.objects.create(
            old_node=old, new_node=new, evidence=evidence, confidence=Link.Confidence.MEDIUM, state=state
        )

    return make


def api(user):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return client


def _list_url(node):
    return reverse("observed-node-identity-links", kwargs={"internal_id": str(node.internal_id)})


def _act_url(link, action):
    return reverse(f"identity-links-{action}", kwargs={"pk": link.pk})


# --- permission helpers: every cell of the table -----------------------------------------------------------------


def _owners(users, who):
    """(old owner, new owner) for a scenario name."""
    return {
        "none": (None, None),
        "old_only": (users["owner_old"], None),
        "new_only": (None, users["owner_new"]),
        "old_vs_new": (users["owner_old"], users["owner_new"]),
        "both_same": (users["owner_both"], users["owner_both"]),
        "old_vs_stranger": (users["owner_old"], users["stranger"]),
    }[who]


CONFIRM_CASES = [
    # scenario, actor, may confirm a suggested link
    ("none", "anon", False),
    ("none", "stranger", False),
    ("none", "staff", True),
    ("old_only", "owner_old", True),  # new row unclaimed
    ("old_only", "stranger", False),
    ("new_only", "owner_new", True),  # old row unclaimed
    ("old_vs_new", "owner_old", False),  # the new row is someone else's
    ("old_vs_new", "owner_new", False),  # the old row is someone else's
    ("old_vs_new", "staff", True),
    ("both_same", "owner_both", True),
    ("both_same", "stranger", False),
]


@pytest.mark.django_db
@pytest.mark.parametrize("scenario, actor, expected", CONFIRM_CASES)
def test_can_confirm_table(users, make_link, scenario, actor, expected):
    old_owner, new_owner = _owners(users, scenario)
    link = make_link(old_owner=old_owner, new_owner=new_owner)
    assert identity_links.can_confirm_link(users[actor], link) is expected


@pytest.mark.django_db
@pytest.mark.parametrize("state", [State.AUTO, State.CONFIRMED, State.REJECTED, State.FLAGGED])
def test_only_a_suggested_link_can_be_confirmed(users, make_link, state):
    link = make_link(state=state if state != State.FLAGGED else State.SUGGESTED)
    if state == State.FLAGGED:
        link.state = State.FLAGGED
    assert identity_links.can_confirm_link(users["staff"], link) is False


REJECT_CASES = [
    ("none", "anon", False),
    ("none", "stranger", False),
    ("none", "staff", True),
    ("old_only", "owner_old", True),
    ("new_only", "owner_new", True),
    ("old_vs_new", "owner_old", True),  # unlike confirm, no claim condition on the other row
    ("old_vs_new", "owner_new", True),
    ("old_only", "stranger", False),
]


@pytest.mark.django_db
@pytest.mark.parametrize("scenario, actor, expected", REJECT_CASES)
def test_can_reject_table(users, make_link, scenario, actor, expected):
    old_owner, new_owner = _owners(users, scenario)
    link = make_link(state=State.AUTO, old_owner=old_owner, new_owner=new_owner)
    assert identity_links.can_reject_link(users[actor], link) is expected


@pytest.mark.django_db
def test_a_rejected_link_cannot_be_rejected_again(users, make_link):
    link = make_link(state=State.REJECTED)
    assert identity_links.can_reject_link(users["staff"], link) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    "scenario, actor, expected",
    [
        ("none", "stranger", False),
        ("none", "anon", False),
        ("none", "staff", True),
        ("old_only", "owner_old", False),  # owns only one of the two
        ("new_only", "owner_new", False),
        ("old_vs_new", "owner_old", False),
        ("both_same", "owner_both", True),
    ],
)
def test_can_declare_table(users, make_link, scenario, actor, expected):
    old_owner, new_owner = _owners(users, scenario)
    link = make_link(old_owner=old_owner, new_owner=new_owner)
    assert identity_links.can_declare_link(users[actor], link.old_node, link.new_node) is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state, scenario, actor, expected",
    [
        (State.AUTO, "none", "anon", True),
        (State.CONFIRMED, "none", "stranger", True),
        (State.SUGGESTED, "none", "stranger", False),
        (State.REJECTED, "none", "stranger", False),
        (State.SUGGESTED, "old_only", "owner_old", True),
        (State.REJECTED, "new_only", "owner_new", True),
        (State.SUGGESTED, "none", "staff", True),
    ],
)
def test_can_see_table(users, make_link, state, scenario, actor, expected):
    old_owner, new_owner = _owners(users, scenario)
    link = make_link(state=state, old_owner=old_owner, new_owner=new_owner)
    assert identity_links.can_see_link(users[actor], link) is expected


@pytest.mark.django_db
def test_a_flagged_row_is_never_visible_or_actionable(users):
    flagged = Link.objects.create(
        evidence=Evidence.PUBLIC_KEY, confidence="strong", state=State.FLAGGED, public_key_hex="ab" * 32
    )
    assert not identity_links.can_see_link(users["staff"], flagged)
    assert not identity_links.can_reject_link(users["staff"], flagged)
    assert not identity_links.can_confirm_link(users["staff"], flagged)


# --- service functions -------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_set_link_state_stamps_reviewer_and_sends_live_once(users, make_link, django_capture_on_commit_callbacks):
    link = make_link()
    seen = []

    def listener(sender, link, **kwargs):
        seen.append((link.pk, link.state))

    identity_link_live.connect(listener, weak=False)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            identity_links.set_link_state(link, State.CONFIRMED, users["staff"])
        link.refresh_from_db()
        assert (link.state, link.reviewed_by, link.reviewed_at is not None) == (State.CONFIRMED, users["staff"], True)
        assert seen == [(link.pk, State.CONFIRMED)]
        with django_capture_on_commit_callbacks(execute=True):
            identity_links.set_link_state(link, State.REJECTED, users["staff"])
        with django_capture_on_commit_callbacks(execute=True):
            identity_links.set_link_state(link, State.SUGGESTED, users["staff"])  # staff undo
        assert len(seen) == 1  # leaving or staying outside the live set sends nothing
    finally:
        identity_link_live.disconnect(listener)


@pytest.mark.django_db
def test_set_link_state_turns_a_second_live_link_into_link_conflict(users, make_link, create_observed_node):
    first = make_link(state=State.AUTO)
    third = create_observed_node(meshtastic_node_id=OTHER)
    second = Link.objects.create(
        old_node=first.old_node, new_node=third, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED
    )
    with pytest.raises(IdentityLinkError) as exc:
        identity_links.set_link_state(second, State.CONFIRMED, users["staff"])
    assert exc.value.code == "link_conflict"
    second.refresh_from_db()
    assert second.state == State.SUGGESTED


@pytest.mark.django_db
def test_set_link_state_refuses_flagged_rows_and_unknown_states(users):
    flagged = Link.objects.create(
        evidence=Evidence.PUBLIC_KEY, confidence="strong", state=State.FLAGGED, public_key_hex="cd" * 32
    )
    with pytest.raises(IdentityLinkError) as exc:
        identity_links.set_link_state(flagged, State.CONFIRMED, users["staff"])
    assert exc.value.code == "invalid_state"
    with pytest.raises(IdentityLinkError):
        identity_links.set_link_state(flagged, "bogus", users["staff"])


@pytest.mark.django_db
def test_confirm_and_reject_service_states(users, make_link):
    suggested = make_link()
    assert identity_links.confirm_link(suggested, users["staff"]).state == State.CONFIRMED
    with pytest.raises(IdentityLinkError) as exc:
        identity_links.confirm_link(suggested, users["staff"])
    assert exc.value.code == "invalid_state"
    assert identity_links.reject_link(suggested, users["staff"]).state == State.REJECTED
    with pytest.raises(IdentityLinkError) as exc:
        identity_links.reject_link(suggested, users["staff"])
    assert exc.value.code == "invalid_state"


@pytest.mark.django_db
def test_declare_link_creates_a_confirmed_declared_link(users, create_observed_node):
    old = create_observed_node(meshtastic_node_id=OLD, claimed_by=users["owner_both"])
    new = create_observed_node(meshtastic_node_id=NEW, claimed_by=users["owner_both"])
    link = identity_links.declare_link(old, new, users["owner_both"])
    assert (link.evidence, link.confidence, link.state) == (Evidence.DECLARED, "strong", State.CONFIRMED)
    assert link.reviewed_by == users["owner_both"] and link.reviewed_at is not None


@pytest.mark.django_db
def test_declare_link_promotes_an_existing_suggestion(users, make_link):
    link = make_link()
    declared = identity_links.declare_link(link.old_node, link.new_node, users["staff"])
    assert declared.pk == link.pk
    assert (declared.state, declared.evidence) == (State.CONFIRMED, Evidence.DECLARED)
    assert declared.reviewed_by == users["staff"]


@pytest.mark.django_db
def test_declare_link_errors(users, make_link, create_observed_node):
    a = create_observed_node(meshtastic_node_id=OLD)
    b = create_observed_node(meshtastic_node_id=NEW)
    mc = create_observed_node(protocol=Protocol.MESHCORE, meshtastic_node_id=None, mc_pubkey="ab" * 32)

    def code(old, new, actor):
        with pytest.raises(IdentityLinkError) as exc:
            identity_links.declare_link(old, new, actor)
        return exc.value.code

    assert code(a, b, users["stranger"]) == "not_owner"
    assert code(a, a, users["staff"]) == "same_node"
    assert code(a, mc, users["staff"]) == "cross_protocol"

    # reverse pair, rejected pair, second live successor
    identity_links.declare_link(a, b, users["staff"])
    assert code(b, a, users["staff"]) == "link_conflict"
    c = create_observed_node(meshtastic_node_id=OTHER)
    assert code(a, c, users["staff"]) == "link_conflict"
    identity_links.reject_link(Link.objects.get(old_node=a, new_node=b), users["staff"])
    with pytest.raises(IdentityLinkError) as exc:
        identity_links.declare_link(a, b, users["staff"])
    assert exc.value.code == "link_conflict" and "rejected" in str(exc.value)


# --- endpoints ---------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_shows_live_links_to_everyone_and_hides_the_rest(users, make_link, create_observed_node):
    live = make_link(state=State.AUTO, old_owner=users["owner_old"])
    node = live.new_node
    extra = create_observed_node(meshtastic_node_id=OTHER)
    suggested = Link.objects.create(
        old_node=extra, new_node=node, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED
    )
    rejected_old = create_observed_node(meshtastic_node_id=OTHER + 1)
    Link.objects.create(
        old_node=rejected_old, new_node=node, evidence=Evidence.MAC, confidence="medium", state=State.REJECTED
    )
    Link.objects.create(evidence=Evidence.PUBLIC_KEY, confidence="strong", state=State.FLAGGED, public_key_hex="ef" * 32)

    def states(user, target=node):
        resp = api(user).get(_list_url(target))
        assert resp.status_code == 200, resp.content
        return [row["state"] for row in resp.data]

    assert states(users["stranger"]) == ["auto"]
    assert states(users["owner_old"]) == ["auto"]  # owns the live link's old row, not the other rows
    assert sorted(states(users["staff"])) == ["auto", "rejected", "suggested"]

    node.claimed_by = users["owner_new"]
    node.save()
    assert sorted(states(users["owner_new"])) == ["auto", "rejected", "suggested"]
    assert suggested.pk in [r["id"] for r in api(users["staff"]).get(_list_url(node)).data]


@pytest.mark.django_db
def test_list_row_shape_order_and_lookup_forms(users, make_link, create_observed_node):
    first = make_link(state=State.CONFIRMED, evidence=Evidence.PUBLIC_KEY)
    newer_old = create_observed_node(meshtastic_node_id=OTHER)
    second = Link.objects.create(
        old_node=newer_old, new_node=first.new_node, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED
    )
    client = api(users["staff"])
    rows = client.get(f"/api/nodes/observed-nodes/!{NEW:08x}/identity-links/").data
    assert [r["id"] for r in rows] == [second.pk, first.pk]  # newest first
    row = rows[1]
    assert set(row) == {
        "id",
        "old",
        "new",
        "evidence",
        "confidence",
        "state",
        "created_at",
        "reviewed_at",
        "can_confirm",
        "can_reject",
    }
    assert set(row["old"]) == {
        "internal_id",
        "protocol",
        "meshtastic_node_id",
        "node_id_str",
        "long_name",
        "short_name",
        "last_heard",
    }
    assert row["old"]["node_id_str"] == f"!{OLD:08x}" and row["new"]["long_name"] == "New"
    assert row["can_confirm"] is False and row["can_reject"] is True
    assert rows[0]["can_confirm"] is True
    # the old side finds it too
    assert len(client.get(_list_url(first.old_node)).data) == 1


@pytest.mark.django_db
def test_list_query_count_is_bounded(users, make_link, create_observed_node):
    link = make_link(state=State.AUTO)
    node = link.new_node
    for i in range(8):
        old = create_observed_node(meshtastic_node_id=OTHER + i, claimed_by=users["owner_old"])
        Link.objects.create(
            old_node=old, new_node=node, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED
        )
    client = api(users["staff"])
    client.get(_list_url(node))  # warm up
    with CaptureQueriesContext(connection) as few:
        client.get(_list_url(node))
    for i in range(8, 16):
        old = create_observed_node(meshtastic_node_id=OTHER + i)
        Link.objects.create(
            old_node=old, new_node=node, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED
        )
    with CaptureQueriesContext(connection) as many:
        assert len(client.get(_list_url(node)).data) == 17
    assert len(many) == len(few)


@pytest.mark.django_db
def test_guest_gets_401_or_403(make_link):
    link = make_link(state=State.AUTO)
    anon = api(None)
    assert anon.get(_list_url(link.new_node)).status_code in (401, 403)
    assert anon.post(_list_url(link.old_node), {"new_node": "x"}, format="json").status_code in (401, 403)
    assert anon.post(_act_url(link, "confirm")).status_code in (401, 403)
    assert anon.post(_act_url(link, "reject")).status_code in (401, 403)


@pytest.mark.django_db
@pytest.mark.parametrize("scenario, actor, expected", CONFIRM_CASES[2:])
def test_confirm_endpoint_follows_the_table(users, make_link, scenario, actor, expected):
    old_owner, new_owner = _owners(users, scenario)
    link = make_link(old_owner=old_owner, new_owner=new_owner)
    resp = api(users[actor]).post(_act_url(link, "confirm"))
    link.refresh_from_db()
    if expected:
        assert resp.status_code == 200, resp.content
        assert resp.data["state"] == "confirmed" and link.reviewed_by == users[actor]
    else:
        assert resp.status_code in (403, 404)
        assert link.state == State.SUGGESTED


@pytest.mark.django_db
def test_confirm_errors(users, make_link):
    other_claimed = make_link(old_owner=users["owner_old"], new_owner=users["owner_new"])
    resp = api(users["owner_old"]).post(_act_url(other_claimed, "confirm"))
    assert (resp.status_code, resp.data["code"]) == (403, "not_owner")
    # a stranger cannot see a suggestion at all
    assert api(users["stranger"]).post(_act_url(other_claimed, "confirm")).status_code == 404
    # a live link owned by a stranger's view: not_owner
    live = make_link(state=State.AUTO, old_n=OTHER, new_n=OTHER + 1)
    resp = api(users["stranger"]).post(_act_url(live, "confirm"))
    assert (resp.status_code, resp.data["code"]) == (403, "not_owner")
    # wrong state for staff and for an owner
    resp = api(users["staff"]).post(_act_url(live, "confirm"))
    assert (resp.status_code, resp.data["code"]) == (409, "invalid_state")
    owned = make_link(state=State.AUTO, old_owner=users["owner_old"], old_n=OTHER + 2, new_n=OTHER + 3)
    resp = api(users["owner_old"]).post(_act_url(owned, "confirm"))
    assert (resp.status_code, resp.data["code"]) == (409, "invalid_state")


@pytest.mark.django_db
def test_confirm_into_a_taken_slot_is_link_conflict(users, make_link, create_observed_node):
    live = make_link(state=State.AUTO)
    third = create_observed_node(meshtastic_node_id=OTHER)
    clash = Link.objects.create(
        old_node=live.old_node, new_node=third, evidence=Evidence.MAC, confidence="medium", state=State.SUGGESTED
    )
    resp = api(users["staff"]).post(_act_url(clash, "confirm"))
    assert (resp.status_code, resp.data["code"]) == (409, "link_conflict")


@pytest.mark.django_db
@pytest.mark.parametrize("scenario, actor, expected", REJECT_CASES[2:])
@pytest.mark.parametrize("state", [State.AUTO, State.SUGGESTED, State.CONFIRMED])
def test_reject_endpoint_follows_the_table(users, make_link, scenario, actor, expected, state):
    old_owner, new_owner = _owners(users, scenario)
    link = make_link(state=state, old_owner=old_owner, new_owner=new_owner)
    resp = api(users[actor]).post(_act_url(link, "reject"))
    link.refresh_from_db()
    if expected:
        assert resp.status_code == 200, resp.content
        assert resp.data["state"] == "rejected" and link.reviewed_by == users[actor]
    else:
        assert resp.status_code in (403, 404)
        assert link.state == state


@pytest.mark.django_db
def test_reject_errors(users, make_link):
    rejected = make_link(state=State.REJECTED)
    resp = api(users["staff"]).post(_act_url(rejected, "reject"))
    assert (resp.status_code, resp.data["code"]) == (409, "invalid_state")
    live = make_link(state=State.AUTO, old_n=OTHER, new_n=OTHER + 1)
    resp = api(users["stranger"]).post(_act_url(live, "reject"))
    assert (resp.status_code, resp.data["code"]) == (403, "not_owner")


@pytest.mark.django_db
def test_flagged_rows_and_missing_links_are_404(users):
    flagged = Link.objects.create(
        evidence=Evidence.PUBLIC_KEY, confidence="strong", state=State.FLAGGED, public_key_hex="12" * 32
    )
    client = api(users["staff"])
    assert client.post(_act_url(flagged, "reject")).status_code == 404
    assert client.post(_act_url(flagged, "confirm")).status_code == 404
    assert client.post(reverse("identity-links-reject", kwargs={"pk": 999999})).status_code == 404


@pytest.mark.django_db
def test_declare_endpoint(users, create_observed_node):
    old = create_observed_node(meshtastic_node_id=OLD, claimed_by=users["owner_both"])
    new = create_observed_node(meshtastic_node_id=NEW, claimed_by=users["owner_both"])
    other = create_observed_node(meshtastic_node_id=OTHER)

    resp = api(users["owner_both"]).post(_list_url(old), {"new_node": str(new.internal_id)}, format="json")
    assert resp.status_code == 201, resp.content
    assert resp.data["evidence"] == "declared" and resp.data["state"] == "confirmed"
    assert resp.data["old"]["node_id_str"] == f"!{OLD:08x}"
    assert Link.objects.get(old_node=old, new_node=new).reviewed_by == users["owner_both"]

    # same pair again: not a second row, a conflict-free repeat is still 201 with the same link
    again = api(users["staff"]).post(_list_url(old), {"new_node": f"!{NEW:08x}"}, format="json")
    assert again.status_code == 201 and again.data["id"] == resp.data["id"]

    # owner of only one row
    mine = create_observed_node(meshtastic_node_id=OTHER + 1, claimed_by=users["owner_old"])
    resp = api(users["owner_old"]).post(_list_url(mine), {"new_node": str(other.internal_id)}, format="json")
    assert (resp.status_code, resp.data["code"]) == (403, "not_owner")
    resp = api(users["stranger"]).post(_list_url(other), {"new_node": str(mine.internal_id)}, format="json")
    assert (resp.status_code, resp.data["code"]) == (403, "not_owner")


@pytest.mark.django_db
def test_declare_endpoint_errors(users, create_observed_node):
    a = create_observed_node(meshtastic_node_id=OLD)
    b = create_observed_node(meshtastic_node_id=NEW)
    c = create_observed_node(meshtastic_node_id=OTHER)
    mc = create_observed_node(protocol=Protocol.MESHCORE, meshtastic_node_id=None, mc_pubkey="cd" * 32)
    staff = api(users["staff"])

    def post(node, body):
        return staff.post(_list_url(node), body, format="json")

    resp = post(a, {"new_node": str(a.internal_id)})
    assert (resp.status_code, resp.data["code"]) == (400, "same_node")
    resp = post(a, {"new_node": str(mc.internal_id)})
    assert (resp.status_code, resp.data["code"]) == (400, "cross_protocol")
    resp = post(a, {"new_node": "!deadbeef"})
    assert (resp.status_code, resp.data["code"]) == (404, "not_found")
    resp = post(a, {})
    assert (resp.status_code, resp.data["code"]) == (404, "not_found")
    assert post(a, {"new_node": str(b.internal_id)}).status_code == 201
    resp = post(b, {"new_node": str(a.internal_id)})  # reverse
    assert (resp.status_code, resp.data["code"]) == (409, "link_conflict")
    resp = post(a, {"new_node": str(c.internal_id)})  # a already has a live successor
    assert (resp.status_code, resp.data["code"]) == (409, "link_conflict")
    # reject sticks, even for staff declaring again
    link = Link.objects.get(old_node=a, new_node=b)
    assert staff.post(_act_url(link, "reject")).status_code == 200
    resp = post(a, {"new_node": str(b.internal_id)})
    assert (resp.status_code, resp.data["code"]) == (409, "link_conflict")
    assert "rejected" in resp.data["detail"]
    assert ObservedNode.objects.count() == 4
