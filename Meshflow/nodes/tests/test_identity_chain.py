"""A node's other identities: nodes.services.identity_chain and its API fields (``identity_chain``, ``replaced_by``)."""

from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.protocol import Protocol
from mesh_monitoring.serializers import ObservedNodeWatchSummarySerializer
from nodes.models import ObservedNode, ObservedNodeIdentityLink
from nodes.serializers import ObservedNodeSerializer
from nodes.services import identity_chain

Link = ObservedNodeIdentityLink
State = Link.State

NOW = timezone.now().replace(microsecond=0)


def _link(old, new, state=State.AUTO, evidence=Link.Evidence.PUBLIC_KEY, confidence=Link.Confidence.STRONG):
    return Link.objects.create(old_node=old, new_node=new, state=state, evidence=evidence, confidence=confidence)


@pytest.fixture
def client(create_user):
    api = APIClient()
    api.force_authenticate(user=create_user())
    return api


@pytest.fixture
def trio(create_observed_node):
    """A -> B -> C, each heard later than the one before."""
    a = create_observed_node(
        meshtastic_node_id=0x100, long_name="A", short_name="A", last_heard=NOW - timedelta(days=3)
    )
    b = create_observed_node(
        meshtastic_node_id=0x200, long_name="B", short_name="B", last_heard=NOW - timedelta(days=2)
    )
    c = create_observed_node(
        meshtastic_node_id=0x300, long_name="C", short_name="C", last_heard=NOW - timedelta(days=1)
    )
    _link(a, b)
    _link(b, c, state=State.CONFIRMED, evidence=Link.Evidence.FEEDER_REKEY)
    return a, b, c


def _detail(client, lookup):
    resp = client.get(reverse("observed-node-detail", kwargs={"internal_id": lookup}))
    assert resp.status_code == 200, resp.content
    return resp.data


def _ids(entries):
    return [e["node_id_str"] for e in entries]


# --- chain() and replaced_by() ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_chain_without_links_is_empty(create_observed_node):
    node = create_observed_node()
    result = identity_chain.chain(node)
    assert result.previous == [] and result.next == []
    assert identity_chain.replaced_by(node) is None


@pytest.mark.django_db
def test_chain_one_link_each_direction(create_observed_node):
    old = create_observed_node(last_heard=NOW - timedelta(days=1))
    new = create_observed_node(last_heard=NOW)
    link = _link(old, new)
    assert [(s.node, s.link) for s in identity_chain.chain(old).next] == [(new, link)]
    assert identity_chain.chain(old).previous == []
    assert [(s.node, s.link) for s in identity_chain.chain(new).previous] == [(old, link)]
    assert identity_chain.chain(new).next == []
    assert identity_chain.replaced_by(old) == new
    assert identity_chain.replaced_by(new) is None


@pytest.mark.django_db
def test_chain_three_nodes_nearest_first(trio):
    a, b, c = trio
    from_a = identity_chain.chain(a)
    assert [s.node for s in from_a.next] == [b, c] and from_a.previous == []
    from_b = identity_chain.chain(b)
    assert [s.node for s in from_b.previous] == [a] and [s.node for s in from_b.next] == [c]
    from_c = identity_chain.chain(c)
    assert [s.node for s in from_c.previous] == [b, a] and from_c.next == []
    assert identity_chain.replaced_by(a) == c
    assert identity_chain.replaced_by(b) == c
    assert identity_chain.replaced_by(c) is None


@pytest.mark.django_db
@pytest.mark.parametrize("state", [State.SUGGESTED, State.REJECTED])
def test_chain_ignores_non_live_links(create_observed_node, state):
    old, new = create_observed_node(), create_observed_node()
    _link(old, new, state=state, evidence=Link.Evidence.MAC, confidence=Link.Confidence.MEDIUM)
    assert identity_chain.chain(old).next == []
    assert identity_chain.chain(new).previous == []


@pytest.mark.django_db
def test_chain_ignores_flagged_rows(create_observed_node):
    node = create_observed_node()
    Link.objects.create(
        state=State.FLAGGED,
        evidence=Link.Evidence.PUBLIC_KEY,
        confidence=Link.Confidence.STRONG,
        public_key_hex="ab" * 32,
        detail={"holders": [node.meshtastic_node_id]},
    )
    result = identity_chain.chain(node)
    assert result.previous == [] and result.next == []


@pytest.mark.django_db
def test_chain_cycle_stops_at_repeat(create_observed_node):
    a, b, c = (create_observed_node() for _ in range(3))
    _link(a, b)
    _link(b, c)
    _link(c, a)  # not prevented by the database
    from_a = identity_chain.chain(a)
    assert [s.node for s in from_a.next] == [b, c]
    assert [s.node for s in from_a.previous] == [c, b]


@pytest.mark.django_db
def test_chain_caps_at_limit(create_observed_node):
    nodes = [create_observed_node() for _ in range(13)]
    for old, new in zip(nodes, nodes[1:]):
        _link(old, new)
    result = identity_chain.chain(nodes[0])
    assert [s.node for s in result.next] == nodes[1:11]
    assert len(identity_chain.chain(nodes[-1]).previous) == 10
    assert len(identity_chain.chain(nodes[0], limit=3).next) == 3


@pytest.mark.django_db
def test_replaced_by_rule_last_heard(create_observed_node):
    old = create_observed_node(last_heard=NOW)
    new = create_observed_node(last_heard=NOW - timedelta(hours=1))
    _link(old, new)
    assert identity_chain.replaced_by(old) is None  # T7: the old row was heard after its successor

    new.last_heard = NOW
    new.save()
    assert identity_chain.replaced_by(ObservedNode.objects.get(pk=old.pk)) == new  # equal counts as replaced


@pytest.mark.django_db
def test_replaced_by_rule_null_last_heard(create_observed_node):
    never = create_observed_node(last_heard=None)
    heard = create_observed_node(last_heard=NOW)
    silent = create_observed_node(last_heard=None)
    _link(never, silent)  # old never heard: replaced even though the successor was not heard either
    assert identity_chain.replaced_by(never) == silent

    old = create_observed_node(last_heard=NOW)
    mute = create_observed_node(last_heard=None)
    _link(old, mute)
    assert identity_chain.replaced_by(old) is None  # successor never heard cannot replace a heard node
    assert heard  # keep the fixture row in the table


# --- detail ----------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_detail_without_links_has_empty_fields(client, create_observed_node):
    node = create_observed_node()
    data = _detail(client, str(node.internal_id))
    assert data["replaced_by"] is None
    assert data["identity_chain"] == {"previous": [], "next": []}


@pytest.mark.django_db
def test_detail_chain_from_each_end(client, trio):
    a, b, c = trio
    from_a = _detail(client, str(a.internal_id))
    assert from_a["replaced_by"]["internal_id"] == str(c.internal_id)
    assert from_a["identity_chain"]["previous"] == []
    assert _ids(from_a["identity_chain"]["next"]) == ["!00000200", "!00000300"]

    from_b = _detail(client, str(b.internal_id))
    assert from_b["replaced_by"]["node_id_str"] == "!00000300"
    assert _ids(from_b["identity_chain"]["previous"]) == ["!00000100"]
    assert _ids(from_b["identity_chain"]["next"]) == ["!00000300"]

    from_c = _detail(client, str(c.internal_id))
    assert from_c["replaced_by"] is None
    assert _ids(from_c["identity_chain"]["previous"]) == ["!00000200", "!00000100"]
    assert from_c["identity_chain"]["next"] == []


@pytest.mark.django_db
def test_detail_entry_shape(client, trio):
    a, b, _ = trio
    entry = _detail(client, str(a.internal_id))["identity_chain"]["next"][0]
    assert entry == {
        "internal_id": str(b.internal_id),
        "protocol": 1,
        "meshtastic_node_id": 0x200,
        "node_id_str": "!00000200",
        "long_name": "B",
        "short_name": "B",
        "last_heard": entry["last_heard"],
        "evidence": "public_key",
        "confidence": "strong",
        "state": "auto",
        "linked_at": entry["linked_at"],
    }
    assert entry["last_heard"].endswith("Z") and entry["linked_at"].endswith("Z")
    ref = _detail(client, str(a.internal_id))["replaced_by"]
    assert set(ref) == {"internal_id", "protocol", "meshtastic_node_id", "node_id_str"}


@pytest.mark.django_db
def test_detail_every_lookup_form(client, trio):
    a, _, c = trio
    for lookup in (str(a.internal_id), "!00000100", "mt:00000100", str(0x100)):
        data = _detail(client, lookup)
        assert data["replaced_by"]["internal_id"] == str(c.internal_id), lookup
        assert len(data["identity_chain"]["next"]) == 2


@pytest.mark.django_db
def test_detail_t7_old_row_heard_after_successor(client, create_observed_node):
    old = create_observed_node(meshtastic_node_id=0x100, last_heard=NOW)
    new = create_observed_node(meshtastic_node_id=0x200, last_heard=NOW - timedelta(hours=2))
    _link(old, new)
    data = _detail(client, str(old.internal_id))
    assert data["replaced_by"] is None
    assert _ids(data["identity_chain"]["next"]) == ["!00000200"]


@pytest.mark.django_db
def test_detail_last_heard_null_cases(client, create_observed_node):
    old = create_observed_node(meshtastic_node_id=0x100, last_heard=None)
    new = create_observed_node(meshtastic_node_id=0x200, last_heard=None)
    _link(old, new)
    assert _detail(client, str(old.internal_id))["replaced_by"]["node_id_str"] == "!00000200"

    heard = create_observed_node(meshtastic_node_id=0x300, last_heard=NOW)
    mute = create_observed_node(meshtastic_node_id=0x400, last_heard=None)
    _link(heard, mute)
    data = _detail(client, str(heard.internal_id))
    assert data["replaced_by"] is None
    assert data["identity_chain"]["next"][0]["last_heard"] is None


@pytest.mark.django_db
def test_detail_ignores_suggested_rejected_and_flagged(client, create_observed_node):
    node = create_observed_node(meshtastic_node_id=0x100)
    other = create_observed_node(meshtastic_node_id=0x200)
    third = create_observed_node(meshtastic_node_id=0x300)
    _link(node, other, state=State.SUGGESTED, evidence=Link.Evidence.MAC, confidence=Link.Confidence.MEDIUM)
    _link(third, node, state=State.REJECTED)
    Link.objects.create(state=State.FLAGGED, evidence="public_key", confidence="strong", public_key_hex="ab" * 32)
    data = _detail(client, str(node.internal_id))
    assert data["replaced_by"] is None
    assert data["identity_chain"] == {"previous": [], "next": []}


@pytest.mark.django_db
def test_detail_meshcore_pair(client, create_observed_node):
    old = create_observed_node(protocol=Protocol.MESHCORE, mc_pubkey="a1" * 32, last_heard=NOW - timedelta(days=1))
    new = create_observed_node(protocol=Protocol.MESHCORE, mc_pubkey="b2" * 32, last_heard=NOW)
    _link(old, new)
    data = _detail(client, str(old.internal_id))
    ref = data["replaced_by"]
    assert ref["protocol"] == 2 and ref["meshtastic_node_id"] is None
    assert ref["node_id_str"].startswith("mc:")
    assert data["identity_chain"]["next"][0]["node_id_str"] == ref["node_id_str"]


@pytest.mark.django_db
def test_detail_ambiguous_lookup_unchanged(client, create_observed_node):
    create_observed_node(protocol=Protocol.MESHTASTIC, meshtastic_node_id=0xAB123456)
    create_observed_node(protocol=Protocol.MESHCORE, mc_pubkey="ab123456" + "0" * 56)
    resp = client.get(reverse("observed-node-detail", kwargs={"internal_id": "ab123456"}))
    assert resp.status_code == 300


@pytest.mark.django_db
def test_detail_query_count_is_bounded(client, trio, create_observed_node):
    a, b, _ = trio
    plain = create_observed_node()
    url = lambda n: reverse("observed-node-detail", kwargs={"internal_id": str(n.internal_id)})  # noqa: E731
    with CaptureQueriesContext(connection) as ctx:
        client.get(url(plain))
    plain_count = len(ctx)
    with CaptureQueriesContext(connection) as ctx:
        client.get(url(b))  # one hop each way: two queries per direction (the hop and the empty end)
    # two lookups per direction (the hop, then the end), against two on a node with no links
    assert len(ctx) == plain_count + 2


# --- list, mine, search ----------------------------------------------------------------------------------------


def _by_id(rows):
    return {r["internal_id"]: r for r in rows}


@pytest.mark.django_db
def test_list_gives_direct_successor(client, trio):
    a, b, c = trio
    rows = _by_id(client.get(reverse("observed-node-list")).data["results"])
    assert rows[str(a.internal_id)]["replaced_by"]["internal_id"] == str(b.internal_id)  # direct, not the newest
    assert rows[str(b.internal_id)]["replaced_by"]["internal_id"] == str(c.internal_id)
    assert rows[str(c.internal_id)]["replaced_by"] is None
    assert "identity_chain" not in rows[str(a.internal_id)]
    ref = rows[str(a.internal_id)]["replaced_by"]
    assert ref == {
        "internal_id": str(b.internal_id),
        "protocol": 1,
        "meshtastic_node_id": 0x200,
        "node_id_str": "!00000200",
    }


@pytest.mark.django_db
def test_list_replaced_false_filter(client, trio, create_observed_node):
    a, b, c = trio
    t7_old = create_observed_node(meshtastic_node_id=0x500, last_heard=NOW)
    t7_new = create_observed_node(meshtastic_node_id=0x600, last_heard=NOW - timedelta(hours=1))
    _link(t7_old, t7_new)
    url = reverse("observed-node-list")
    ids = {r["internal_id"] for r in client.get(url, {"replaced": "false"}).data["results"]}
    assert str(a.internal_id) not in ids and str(b.internal_id) not in ids
    assert {str(c.internal_id), str(t7_old.internal_id), str(t7_new.internal_id)} <= ids
    for ignored in ("true", "1", ""):
        every = {r["internal_id"] for r in client.get(url, {"replaced": ignored}).data["results"]}
        assert str(a.internal_id) in every


@pytest.mark.django_db
def test_list_t7_row_keeps_null_replaced_by(client, create_observed_node):
    old = create_observed_node(last_heard=NOW)
    new = create_observed_node(last_heard=NOW - timedelta(hours=1))
    _link(old, new)
    rows = _by_id(client.get(reverse("observed-node-list")).data["results"])
    assert rows[str(old.internal_id)]["replaced_by"] is None


@pytest.mark.django_db
def test_list_meshcore_successor(client, create_observed_node):
    old = create_observed_node(protocol=Protocol.MESHCORE, mc_pubkey="a1" * 32, last_heard=None)
    new = create_observed_node(protocol=Protocol.MESHCORE, mc_pubkey="b2" * 32, last_heard=NOW)
    _link(old, new)
    rows = _by_id(client.get(reverse("observed-node-list")).data["results"])
    ref = rows[str(old.internal_id)]["replaced_by"]
    assert ref["meshtastic_node_id"] is None and ref["protocol"] == 2 and ref["node_id_str"].startswith("mc:")


@pytest.mark.django_db
def test_mine_and_search_have_replaced_by(create_user, create_observed_node):
    user = create_user()
    api = APIClient()
    api.force_authenticate(user=user)
    old = create_observed_node(meshtastic_node_id=0x100, long_name="findme old", claimed_by=user, last_heard=None)
    new = create_observed_node(meshtastic_node_id=0x200, long_name="findme new", claimed_by=user, last_heard=NOW)
    _link(old, new)

    mine = _by_id(api.get(reverse("observed-node-mine")).data["results"])
    assert mine[str(old.internal_id)]["replaced_by"]["internal_id"] == str(new.internal_id)
    assert mine[str(new.internal_id)]["replaced_by"] is None
    assert "identity_chain" not in mine[str(old.internal_id)]

    found = _by_id(api.get(reverse("observed-node-search"), {"q": "findme"}).data)
    assert found[str(old.internal_id)]["replaced_by"]["node_id_str"] == "!00000200"
    assert found[str(new.internal_id)]["replaced_by"] is None
    assert "identity_chain" not in found[str(old.internal_id)]


@pytest.mark.django_db
@pytest.mark.parametrize("with_links", [False, True])
def test_list_mine_search_query_counts_match_main(create_user, create_observed_node, with_links):
    """Pinned to the counts the same requests cost on main (list 34, mine 42, search 5) before this change."""
    user = create_user()
    api = APIClient()
    api.force_authenticate(user=user)
    nodes = [
        create_observed_node(meshtastic_node_id=1000 + i, claimed_by=user, long_name=f"n{i}", last_heard=None)
        for i in range(4)
    ]
    if with_links:
        _link(nodes[0], nodes[1])
        _link(nodes[1], nodes[2])

    def count(url):
        with CaptureQueriesContext(connection) as ctx:
            assert api.get(url).status_code == 200
        return len(ctx)

    assert count(reverse("observed-node-list")) == 34
    assert count(reverse("observed-node-mine")) == 42
    assert count(reverse("observed-node-search") + "?q=n") == 5


# --- payloads that must not change -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_other_payloads_have_no_replaced_by(client, create_observed_node, create_user):
    from nodes.models import RoleSource

    old = create_observed_node(meshtastic_role=RoleSource.ROUTER, last_heard=NOW - timedelta(days=1))
    new = create_observed_node(meshtastic_role=RoleSource.ROUTER, last_heard=NOW)
    _link(old, new)

    infra = client.get("/api/nodes/observed-nodes/infrastructure/")
    assert infra.status_code == 200 and infra.data["results"]
    assert all("replaced_by" not in r and "identity_chain" not in r for r in infra.data["results"])

    nearby = client.get("/api/nodes/observed-nodes/infrastructure/nearby/", {"lat": 55.0, "lon": -4.0, "radius_km": 50})
    assert nearby.status_code == 200
    assert all("replaced_by" not in r for r in (nearby.data.get("results") or nearby.data))

    weather = client.get("/api/nodes/observed-nodes/weather/")
    assert weather.status_code == 200
    assert all("replaced_by" not in r for r in weather.data.get("results", weather.data))

    # traceroute target_node and monitoring watch payloads reuse the base serializers
    assert "replaced_by" not in ObservedNodeSerializer(old).data
    assert "replaced_by" not in ObservedNodeWatchSummarySerializer(old).data


# --- a predicted-only link does not count as replaced -----------------------------------------------------

KEY = "ab" * 32


@pytest.fixture
def predicted_pair(create_user, create_observed_node):
    user = create_user()
    old = create_observed_node(meshtastic_node_id=0x500, long_name="p old", claimed_by=user, last_heard=NOW)
    new = create_observed_node(meshtastic_node_id=0x600, long_name="p new", claimed_by=user, last_heard=NOW)
    link = _link(old, new, evidence=Link.Evidence.PREDICTED_NUMBER, confidence=Link.Confidence.MEDIUM)
    link.public_key_hex = KEY
    link.save(update_fields=["public_key_hex"])
    return user, old, new, link


def _replaced_everywhere(user, old):
    """The replaced_by seen on detail, list, mine and search, and whether ?replaced=false keeps the old row."""
    api = APIClient()
    api.force_authenticate(user=user)
    detail = api.get(reverse("observed-node-detail", kwargs={"internal_id": old.internal_id})).data
    key = str(old.internal_id)
    lst = _by_id(api.get(reverse("observed-node-list")).data["results"])
    mine = _by_id(api.get(reverse("observed-node-mine")).data["results"])
    found = _by_id(api.get(reverse("observed-node-search"), {"q": "p old"}).data)
    kept = {r["internal_id"] for r in api.get(reverse("observed-node-list"), {"replaced": "false"}).data["results"]}
    refs = [detail["replaced_by"], lst[key]["replaced_by"], mine[key]["replaced_by"], found[key]["replaced_by"]]
    return refs, key in kept, detail


@pytest.mark.django_db
def test_predicted_only_link_is_not_replaced_anywhere(predicted_pair):
    user, old, new, link = predicted_pair
    refs, kept, detail = _replaced_everywhere(user, old)
    assert refs == [None, None, None, None]
    assert kept
    assert identity_chain.replaced_by(old) is None
    # still recorded and still in identity_chain, with its evidence visible
    entry = detail["identity_chain"]["next"][0]
    assert entry["internal_id"] == str(new.internal_id)
    assert entry["evidence"] == "predicted_number"


@pytest.mark.django_db
def test_predicted_link_counts_once_new_key_is_heard(predicted_pair):
    user, old, new, link = predicted_pair
    new.meshtastic_public_key_hex = KEY
    new.save(update_fields=["meshtastic_public_key_hex"])
    refs, kept, _ = _replaced_everywhere(user, old)
    assert all(r and r["internal_id"] == str(new.internal_id) for r in refs)
    assert not kept


@pytest.mark.django_db
def test_predicted_link_with_a_different_new_key_is_not_replaced(predicted_pair):
    user, old, new, link = predicted_pair
    # the new row holds some other key and demotion has not run: the link still must not count
    new.meshtastic_public_key_hex = "cd" * 32
    new.save(update_fields=["meshtastic_public_key_hex"])
    refs, kept, _ = _replaced_everywhere(user, old)
    assert refs == [None, None, None, None]
    assert kept
    assert identity_chain.replaced_by(old) is None


@pytest.mark.django_db
def test_other_evidence_without_key_still_counts(create_observed_node):
    old = create_observed_node(last_heard=NOW - timedelta(hours=1))
    new = create_observed_node(last_heard=NOW)
    for evidence in (Link.Evidence.FEEDER_REKEY, Link.Evidence.DECLARED):
        Link.objects.all().delete()
        _link(old, new, evidence=evidence)
        assert identity_chain.replaced_by(old) == new
        assert not ObservedNode.objects.exclude(identity_chain.replaced_q()).filter(pk=old.pk).exists()
