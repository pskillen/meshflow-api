"""A key may be linked to only one active feeder; existing shared links keep working (#438)."""

from types import SimpleNamespace

from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from common.access import grant_feeder_role
from nodes.api_key_linking import API_KEY_ALREADY_LINKED_CODE, API_KEY_ALREADY_LINKED_MESSAGE, api_key_can_link
from nodes.models import ManagedNode, NodeAPIKey, NodeAuth
from nodes.permissions import NodeAuthorizationPermission


@pytest.fixture
def setup(create_user, create_constellation, create_managed_node, create_node_api_key):
    owner = create_user()
    grant_feeder_role(owner)
    constellation = create_constellation(created_by=owner)
    node_a = create_managed_node(owner=owner, constellation=constellation)
    node_b = create_managed_node(owner=owner, constellation=constellation)
    api_key = create_node_api_key(owner=owner, constellation=constellation)
    client = APIClient()
    client.force_authenticate(user=owner)
    return SimpleNamespace(owner=owner, constellation=constellation, a=node_a, b=node_b, key=api_key, client=client)


def _add(s, node, key=None):
    return s.client.post(
        reverse("api-keys-add-node", kwargs={"pk": (key or s.key).id}),
        {"managed_node_internal_id": str(node.internal_id)},
        format="json",
    )


@pytest.mark.django_db
def test_add_first_node_ok(setup):
    assert _add(setup, setup.a).status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_add_second_node_blocked(setup):
    assert _add(setup, setup.a).status_code == status.HTTP_201_CREATED
    resp = _add(setup, setup.b)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data == {"error": API_KEY_ALREADY_LINKED_MESSAGE, "code": API_KEY_ALREADY_LINKED_CODE}
    assert API_KEY_ALREADY_LINKED_CODE == "api_key_already_linked"
    assert NodeAuth.objects.filter(api_key=setup.key).count() == 1


@pytest.mark.django_db
def test_add_same_node_again_keeps_existing_error(setup):
    _add(setup, setup.a)
    resp = _add(setup, setup.a)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data == {"error": "Node is already linked to this API key"}


@pytest.mark.django_db
def test_readd_after_remove_works(setup):
    _add(setup, setup.a)
    resp = setup.client.post(
        reverse("api-keys-remove-node", kwargs={"pk": setup.key.id}),
        {"managed_node_internal_id": str(setup.a.internal_id)},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    assert _add(setup, setup.b).status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_soft_deleted_old_link_does_not_count(setup):
    NodeAuth.objects.create(api_key=setup.key, node=setup.a)
    ManagedNode.objects.filter(pk=setup.a.pk).update(deleted_at=timezone.now())
    assert api_key_can_link(setup.key, setup.b) is True
    assert _add(setup, setup.b).status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_feeder_may_hold_two_keys(setup, create_node_api_key):
    key2 = create_node_api_key(owner=setup.owner, constellation=setup.constellation, name="Second")
    assert _add(setup, setup.a).status_code == status.HTTP_201_CREATED
    assert _add(setup, setup.a, key=key2).status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_existing_shared_key_can_still_be_edited_and_trimmed(setup):
    NodeAuth.objects.create(api_key=setup.key, node=setup.a)
    NodeAuth.objects.create(api_key=setup.key, node=setup.b)
    resp = setup.client.patch(reverse("api-keys-detail", kwargs={"pk": setup.key.id}), {"name": "x"}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    resp = setup.client.post(
        reverse("api-keys-remove-node", kwargs={"pk": setup.key.id}),
        {"managed_node_internal_id": str(setup.b.internal_id)},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_create_with_two_nodes_blocked_and_no_key_row(setup):
    before = NodeAPIKey.objects.count()
    resp = setup.client.post(
        reverse("api-keys-list"),
        {
            "name": "shared",
            "constellation": setup.constellation.id,
            "managed_node_internal_ids": [str(setup.a.internal_id), str(setup.b.internal_id)],
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data == {"error": API_KEY_ALREADY_LINKED_MESSAGE, "code": API_KEY_ALREADY_LINKED_CODE}
    assert NodeAPIKey.objects.count() == before


@pytest.mark.django_db
def test_create_with_mixed_lists_counts_total(setup):
    resp = setup.client.post(
        reverse("api-keys-list"),
        {
            "name": "shared",
            "constellation": setup.constellation.id,
            "nodes": [setup.a.meshtastic_node_id],
            "managed_node_internal_ids": [str(setup.b.internal_id)],
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == API_KEY_ALREADY_LINKED_CODE


@pytest.mark.django_db
def test_create_with_one_node_works(setup):
    resp = setup.client.post(
        reverse("api-keys-list"),
        {"name": "one", "constellation": setup.constellation.id, "nodes": [setup.a.meshtastic_node_id]},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    assert NodeAuth.objects.filter(api_key_id=resp.data["id"], node=setup.a).exists()


@pytest.mark.django_db
def test_existing_shared_key_still_authorises_legacy_urls(setup):
    NodeAuth.objects.create(api_key=setup.key, node=setup.a)
    NodeAuth.objects.create(api_key=setup.key, node=setup.b)
    perm = NodeAuthorizationPermission()
    for node in (setup.a, setup.b):
        request = SimpleNamespace(auth=setup.key)
        view = SimpleNamespace(kwargs={"node_id": node.meshtastic_node_id})
        assert perm.has_permission(request, view) is True
        assert request.auth.node == node
