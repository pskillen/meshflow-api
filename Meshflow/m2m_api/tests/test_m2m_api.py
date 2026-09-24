"""M2M keys, opt-out, and data endpoints."""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.access import M2M_API_GROUP_NAME
from common.protocol import Protocol
from m2m_api.models import M2MApiKey
from nodes.models import RoleSource
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
