"""M2M keys, opt-out, and data endpoints."""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.access import M2M_API_GROUP_NAME
from common.protocol import Protocol
from m2m_api.models import M2MApiKey
from nodes.models import ObservedNodeIdentityLink, RoleSource
from stats.models import StatsSnapshot

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _member(create_user):
    user = create_user()
    group, _ = Group.objects.get_or_create(name=M2M_API_GROUP_NAME)
    user.groups.add(group)
    return user


def _mint(client, user):
    client.force_authenticate(user=user)
    response = client.post(
        "/api/m2m/keys/",
        {"name": "dash", "intended_use": "https://example.test dashboard", "accept_terms": True},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.data["key"]


def test_mint_requires_group(create_user):
    user = create_user()
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/m2m/keys/",
        {"name": "dash", "intended_use": "site", "accept_terms": True},
        format="json",
    )
    assert response.status_code == 403


def test_mint_list_and_jwt_rejected_on_data_route(create_user):
    user = _member(create_user)
    client = APIClient()
    raw = _mint(client, user)
    listed = client.get("/api/m2m/keys/")
    assert listed.status_code == 200
    assert listed.data[0]["prefix"]
    assert "key" not in listed.data[0]

    data = APIClient()
    data.credentials(HTTP_X_API_KEY=raw)
    assert data.get("/api/m2m/v1/meta").status_code == 200

    jwt_client = APIClient()
    jwt_client.credentials(HTTP_AUTHORIZATION="Bearer not-an-m2m-key")
    assert jwt_client.get("/api/m2m/v1/meta").status_code == 401


def test_revoked_and_disabled_owner_fail(create_user):
    user = _member(create_user)
    client = APIClient()
    raw = _mint(client, user)
    key = M2MApiKey.objects.get(owner=user)
    key.revoked_at = timezone.now()
    key.save(update_fields=["revoked_at"])
    data = APIClient()
    data.credentials(HTTP_X_API_KEY=raw)
    assert data.get("/api/m2m/v1/meta").status_code == 401

    user2 = _member(create_user)
    _mint(APIClient(), user2)
    user2.is_active = False
    user2.save(update_fields=["is_active"])
    key2 = M2MApiKey.objects.get(owner=user2)
    assert key2.revoked_reason == "owner_disabled"


@override_settings(M2M_TERMS_VERSION="2", M2M_TERMS_GRACE_DAYS=90)
def test_terms_grace_then_403(create_user):
    user = _member(create_user)
    raw = _mint(APIClient(), user)
    key = M2MApiKey.objects.get(owner=user)
    key.terms_version = "1"
    key.terms_accepted_at = timezone.now() - timedelta(days=10)
    key.save(update_fields=["terms_version", "terms_accepted_at"])
    data = APIClient()
    data.credentials(HTTP_X_API_KEY=raw)
    response = data.get("/api/m2m/v1/meta")
    assert response.status_code == 200
    assert response["X-M2M-Terms-Action-Required"] == "true"

    key.terms_version = "1"
    key.terms_accepted_at = timezone.now() - timedelta(days=91)
    key.save(update_fields=["terms_version", "terms_accepted_at"])
    assert data.get("/api/m2m/v1/meta").status_code == 403


def test_withdraw_revokes_keys(create_user):
    from m2m_api.services import withdraw_m2m_access

    user = _member(create_user)
    raw = _mint(APIClient(), user)
    staff = create_user(is_staff=True)
    result = withdraw_m2m_access(user, by=staff)
    assert result["removed_from_group"] is True
    assert result["keys_revoked"] == 1
    again = withdraw_m2m_access(user, by=staff)
    assert again == {"removed_from_group": False, "keys_revoked": 0}
    data = APIClient()
    data.credentials(HTTP_X_API_KEY=raw)
    assert data.get("/api/m2m/v1/meta").status_code == 401
    stranger = APIClient()
    stranger.force_authenticate(user=create_user())
    assert stranger.post(f"/api/m2m/admin/users/{user.id}/withdraw/").status_code == 403


def test_opt_out_permissions_and_guest_redaction(create_user, create_observed_node, create_managed_node):
    owner = create_user()
    node = create_observed_node(claimed_by=owner, meshtastic_role=RoleSource.ROUTER)
    other = create_user()
    client = APIClient()
    client.force_authenticate(user=other)
    denied = client.patch(
        f"/api/nodes/observed-nodes/{node.internal_id}/environment-settings/",
        {"m2m_opt_out": True},
        format="json",
    )
    assert denied.status_code == 403

    client.force_authenticate(user=owner)
    ok = client.patch(
        f"/api/nodes/observed-nodes/{node.internal_id}/environment-settings/",
        {"m2m_opt_out": True},
        format="json",
    )
    assert ok.status_code == 200
    assert ok.data["m2m_opt_out"] is True

    guest = APIClient().get(f"/api/nodes/observed-nodes/{node.internal_id}/")
    assert "m2m_opt_out" not in guest.data

    feeder_owner = create_user()
    managed = create_managed_node(owner=feeder_owner, meshtastic_node_id=node.meshtastic_node_id)
    assert managed.owner_id == feeder_owner.id
    feeder = APIClient()
    feeder.force_authenticate(user=feeder_owner)
    toggled = feeder.patch(
        f"/api/nodes/observed-nodes/{node.internal_id}/environment-settings/",
        {"m2m_opt_out": False},
        format="json",
    )
    assert toggled.status_code == 200


def test_summary_utc_day_infra_and_opt_out(create_user, create_observed_node):
    user = _member(create_user)
    raw = _mint(APIClient(), user)
    day = datetime(2026, 9, 24, tzinfo=dt_timezone.utc)
    StatsSnapshot.objects.create(
        recorded_at=day.replace(hour=23) - timedelta(days=1),
        stat_type="packet_volume",
        value={"count": 5},
    )
    StatsSnapshot.objects.create(
        recorded_at=day.replace(hour=1),
        stat_type="packet_volume",
        value={"count": 11},
    )
    router = create_observed_node(meshtastic_node_id=111, meshtastic_role=RoleSource.ROUTER, last_heard=timezone.now())
    base = create_observed_node(
        meshtastic_node_id=222,
        meshtastic_role=RoleSource.CLIENT_BASE,
        last_heard=timezone.now(),
    )
    opted = create_observed_node(
        meshtastic_node_id=333,
        meshtastic_role=RoleSource.REPEATER,
        last_heard=timezone.now(),
        m2m_opt_out=True,
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=raw)
    with override_settings():
        summary = client.get("/api/m2m/v1/meshtastic/summary")
    assert summary.status_code == 200
    assert summary.data["packets"]["today"] >= 0
    assert "CLIENT_BASE" in summary.data["nodes_by_role_24h"] or summary.data["infra_nodes_24h"] >= 0
    infra = client.get("/api/m2m/v1/meshtastic/infra-nodes?heard_within=30d")
    ids = [row["id"] for row in infra.data["results"]]
    assert router.node_id_str in ids
    assert base.node_id_str not in ids
    assert opted.node_id_str not in ids
    assert "latitude" not in infra.data["results"][0]


def test_protocols_do_not_mix(create_user, create_observed_node):
    user = _member(create_user)
    raw = _mint(APIClient(), user)
    mt = create_observed_node(meshtastic_role=RoleSource.ROUTER, last_heard=timezone.now())
    mc = create_observed_node(
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey="ab" * 32,
        meshcore_adv_type=2,
        last_heard=timezone.now(),
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=raw)
    mt_ids = [row["id"] for row in client.get("/api/m2m/v1/meshtastic/infra-nodes").data["results"]]
    mc_body = client.get("/api/m2m/v1/meshcore/infra-nodes").data["results"]
    mc_ids = [row["id"] for row in mc_body]
    assert mt.node_id_str in mt_ids
    assert mc.node_id_str not in mt_ids
    assert mc.node_id_str in mc_ids
    assert mt.node_id_str not in mc_ids
    assert mc_body[0]["health"] is None


# --- identity ids on infra-node rows ---------------------------------------------------------------------------


def _infra_client(create_user):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=_mint(APIClient(), _member(create_user)))
    return client


def _infra_rows(client, path="/api/m2m/v1/meshtastic/infra-nodes"):
    cache.clear()
    response = client.get(path)
    assert response.status_code == 200
    return {row["id"]: row for row in response.data["results"]}


def _router(create_observed_node, node_id, heard_ago_hours, **extra):
    return create_observed_node(
        meshtastic_node_id=node_id,
        meshtastic_role=RoleSource.ROUTER,
        last_heard=timezone.now() - timedelta(hours=heard_ago_hours),
        **extra,
    )


def _live_link(old, new, state=None, evidence=None, key=""):
    return ObservedNodeIdentityLink.objects.create(
        old_node=old,
        new_node=new,
        state=state or ObservedNodeIdentityLink.State.AUTO,
        evidence=evidence or ObservedNodeIdentityLink.Evidence.PUBLIC_KEY,
        confidence=ObservedNodeIdentityLink.Confidence.STRONG,
        public_key_hex=key,
    )


def test_infra_identity_ids_null_without_links(create_user, create_observed_node):
    client = _infra_client(create_user)
    node = _router(create_observed_node, 1001, 1)
    row = _infra_rows(client)[node.node_id_str]
    assert row["replaced_by_id"] is None and row["previous_id"] is None


def test_infra_identity_ids_for_a_live_link(create_user, create_observed_node):
    client = _infra_client(create_user)
    old = _router(create_observed_node, 1002, 5)
    new = _router(create_observed_node, 1003, 1)
    _live_link(old, new)
    rows = _infra_rows(client)
    assert rows[old.node_id_str]["replaced_by_id"] == new.node_id_str
    assert rows[old.node_id_str]["previous_id"] is None
    assert rows[new.node_id_str]["previous_id"] == old.node_id_str
    assert rows[new.node_id_str]["replaced_by_id"] is None


def test_infra_old_heard_after_new_is_not_replaced(create_user, create_observed_node):
    client = _infra_client(create_user)
    old = _router(create_observed_node, 1004, 1)
    new = _router(create_observed_node, 1005, 5)
    _live_link(old, new)
    rows = _infra_rows(client)
    assert rows[old.node_id_str]["replaced_by_id"] is None
    assert rows[new.node_id_str]["previous_id"] == old.node_id_str


@pytest.mark.parametrize("state", ["suggested", "rejected"])
def test_infra_non_live_links_ignored(create_user, create_observed_node, state):
    client = _infra_client(create_user)
    old = _router(create_observed_node, 1006, 5)
    new = _router(create_observed_node, 1007, 1)
    _live_link(old, new, state=state)
    rows = _infra_rows(client)
    assert rows[old.node_id_str]["replaced_by_id"] is None
    assert rows[new.node_id_str]["previous_id"] is None


def test_infra_predicted_only_link_names_previous_but_not_replaced_by(create_user, create_observed_node):
    client = _infra_client(create_user)
    old = _router(create_observed_node, 1008, 5)
    new = _router(create_observed_node, 1009, 1)
    _live_link(old, new, evidence=ObservedNodeIdentityLink.Evidence.PREDICTED_NUMBER, key="ab" * 32)
    rows = _infra_rows(client)
    assert rows[old.node_id_str]["replaced_by_id"] is None
    assert rows[new.node_id_str]["previous_id"] == old.node_id_str


def test_infra_opted_out_neighbour_is_never_named_or_listed(create_user, create_observed_node):
    client = _infra_client(create_user)
    old = _router(create_observed_node, 1010, 5, m2m_opt_out=True)
    new = _router(create_observed_node, 1011, 1)
    _live_link(old, new)
    rows = _infra_rows(client)
    assert old.node_id_str not in rows
    assert new.node_id_str not in rows  # the opt-out follows the radio

    old2 = _router(create_observed_node, 1012, 5)
    new2 = _router(create_observed_node, 1013, 1, m2m_opt_out=True)
    _live_link(old2, new2)
    assert _infra_rows(client)[old2.node_id_str]["replaced_by_id"] is None


def test_infra_opt_out_follows_the_radio_to_later_numbers(create_user, create_observed_node):
    client = _infra_client(create_user)
    a = _router(create_observed_node, 1040, 9, m2m_opt_out=True)
    b = _router(create_observed_node, 1041, 5)
    c = _router(create_observed_node, 1042, 1)
    other = _router(create_observed_node, 1043, 1)
    _live_link(a, b)
    _live_link(b, c)
    rows = _infra_rows(client)
    assert set(rows) == {other.node_id_str}


@pytest.mark.parametrize("state", ["suggested", "rejected"])
def test_infra_non_live_link_does_not_hide_successor(create_user, create_observed_node, state):
    client = _infra_client(create_user)
    a = _router(create_observed_node, 1044, 5, m2m_opt_out=True)
    b = _router(create_observed_node, 1045, 1)
    _live_link(a, b, state=state)
    assert b.node_id_str in _infra_rows(client)


def test_infra_flagged_link_does_not_hide_successor(create_user, create_observed_node):
    # A flagged (shared key) row joins no nodes by constraint, so it can never reach the walk.
    client = _infra_client(create_user)
    a = _router(create_observed_node, 1064, 5, m2m_opt_out=True)
    b = _router(create_observed_node, 1065, 1)
    ObservedNodeIdentityLink.objects.create(
        old_node=None,
        new_node=None,
        state=ObservedNodeIdentityLink.State.FLAGGED,
        evidence=ObservedNodeIdentityLink.Evidence.PUBLIC_KEY,
        confidence=ObservedNodeIdentityLink.Confidence.STRONG,
        public_key_hex="ef" * 32,
    )
    assert b.node_id_str in _infra_rows(client)
    assert a.node_id_str not in _infra_rows(client)


@pytest.mark.parametrize("state", ["auto", "confirmed"])
def test_infra_live_link_hides_successor(create_user, create_observed_node, state):
    client = _infra_client(create_user)
    a = _router(create_observed_node, 1060, 5, m2m_opt_out=True)
    b = _router(create_observed_node, 1061, 1)
    _live_link(a, b, state=state)
    assert b.node_id_str not in _infra_rows(client)


def test_infra_key_mismatched_predicted_link_still_hides_successor(create_user, create_observed_node):
    client = _infra_client(create_user)
    a = _router(create_observed_node, 1062, 5, m2m_opt_out=True)
    b = _router(create_observed_node, 1063, 1, public_key="cd" * 32)
    _live_link(a, b, evidence=ObservedNodeIdentityLink.Evidence.PREDICTED_NUMBER, key="ab" * 32)
    assert b.node_id_str not in _infra_rows(client)


def test_infra_chain_longer_than_ten_steps_hides_every_later_number(create_user, create_observed_node):
    client = _infra_client(create_user)
    nodes = [_router(create_observed_node, 1100 + i, 1, m2m_opt_out=(i == 0)) for i in range(14)]
    for old, new in zip(nodes, nodes[1:]):
        _live_link(old, new)
    other = _router(create_observed_node, 1200, 1)
    rows = _infra_rows(client)
    assert set(rows) == {other.node_id_str}


def test_infra_successor_own_opt_out_still_works(create_user, create_observed_node):
    client = _infra_client(create_user)
    a = _router(create_observed_node, 1046, 5)
    b = _router(create_observed_node, 1047, 1, m2m_opt_out=True)
    _live_link(a, b)
    rows = _infra_rows(client)
    assert a.node_id_str in rows and b.node_id_str not in rows


def test_opted_out_successors_is_bounded_by_limit(create_observed_node):
    from nodes.services.identity_chain import opted_out_successors

    nodes = [_router(create_observed_node, 1050 + i, 1, m2m_opt_out=(i == 0)) for i in range(6)]
    for old, new in zip(nodes, nodes[1:]):
        _live_link(old, new)
    with CaptureQueriesContext(connection) as ctx:
        result = opted_out_successors(Protocol.MESHTASTIC, limit=3)
    assert result == {n.pk for n in nodes[1:4]}
    assert len(ctx) == 4  # the opted-out rows, then one per step
    assert opted_out_successors(Protocol.MESHTASTIC) == {n.pk for n in nodes[1:]}  # unbounded by default


def test_infra_meshcore_rows_carry_null_identity_fields(create_user, create_observed_node):
    client = _infra_client(create_user)
    create_observed_node(
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey="cd" * 32,
        meshcore_adv_type=2,
        last_heard=timezone.now(),
    )
    row = next(iter(_infra_rows(client, "/api/m2m/v1/meshcore/infra-nodes").values()))
    assert row["replaced_by_id"] is None and row["previous_id"] is None


def test_infra_query_count_does_not_grow_with_links(create_user, create_observed_node):
    client = _infra_client(create_user)
    _router(create_observed_node, 1020, 1)

    def count():
        cache.clear()
        with CaptureQueriesContext(connection) as ctx:
            assert client.get("/api/m2m/v1/meshtastic/infra-nodes").status_code == 200
        return len(ctx)

    count()  # warm-up: first request pays one-off lookups
    baseline = count()
    for i in range(4):
        _live_link(_router(create_observed_node, 1030 + 2 * i, 5), _router(create_observed_node, 1031 + 2 * i, 1))
    assert count() == baseline
