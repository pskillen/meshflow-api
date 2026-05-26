"""ManagedNode protocol identity (#362): MT vs MC field rules and REST contract."""

from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from common.protocol import Protocol
from nodes.models import ManagedNode


@pytest.mark.django_db
def test_create_two_meshcore_feeders_same_constellation(create_user, create_constellation):
    user = create_user()
    constellation = create_constellation(protocol=Protocol.MESHCORE, created_by=user)
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("managed-nodes-list")

    r1 = client.post(
        url,
        {
            "name": "MC A",
            "constellation_id": constellation.id,
            "protocol": Protocol.MESHCORE,
            "mc_pubkey": "a" * 64,
            "default_location_latitude": 55.0,
            "default_location_longitude": -3.0,
        },
        format="json",
    )
    r2 = client.post(
        url,
        {
            "name": "MC B",
            "constellation_id": constellation.id,
            "protocol": Protocol.MESHCORE,
            "mc_pubkey": "b" * 64,
            "default_location_latitude": 55.1,
            "default_location_longitude": -3.1,
        },
        format="json",
    )

    assert r1.status_code == status.HTTP_201_CREATED, r1.data
    assert r2.status_code == status.HTTP_201_CREATED, r2.data
    assert r1.data["meshtastic_node_id"] is None
    assert r2.data["meshtastic_node_id"] is None
    assert ManagedNode.objects.filter(protocol=Protocol.MESHCORE, deleted_at__isnull=True).count() == 2


@pytest.mark.django_db
def test_managed_node_detail_and_patch_by_internal_id(create_user, create_managed_node):
    user = create_user()
    node = create_managed_node(
        owner=user,
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey="c" * 64,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("managed-nodes-detail", kwargs={"internal_id": node.internal_id})

    get_resp = client.get(url)
    assert get_resp.status_code == status.HTTP_200_OK
    assert get_resp.data["mc_pubkey"] == "c" * 64

    patch_resp = client.patch(url, {"name": "renamed"}, format="json")
    assert patch_resp.status_code == status.HTTP_200_OK
    node.refresh_from_db()
    assert node.name == "renamed"


@pytest.mark.django_db
def test_meshtastic_detail_compat_numeric_lookup(create_user, create_managed_node):
    user = create_user()
    node = create_managed_node(owner=user, meshtastic_node_id=42424242, protocol=Protocol.MESHTASTIC)
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("managed-nodes-detail", kwargs={"internal_id": node.meshtastic_node_id})

    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["internal_id"] == str(node.internal_id)


@pytest.mark.django_db
def test_api_key_add_node_by_internal_id(create_user, create_managed_node, create_node_api_key):
    from common.access import grant_feeder_role

    user = create_user()
    grant_feeder_role(user)
    constellation = create_managed_node(
        protocol=Protocol.MESHCORE,
        mc_pubkey="d" * 64,
    ).constellation
    node_a = create_managed_node(
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_pubkey="e" * 64,
    )
    node_b = create_managed_node(
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_pubkey="f" * 64,
    )
    api_key = create_node_api_key(constellation=constellation, owner=user)
    client = APIClient()
    client.force_authenticate(user=user)

    for managed in (node_a, node_b):
        resp = client.post(
            reverse("api-keys-add-node", kwargs={"pk": api_key.id}),
            {"managed_node_internal_id": str(managed.internal_id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data

    detail = client.get(reverse("api-keys-detail", kwargs={"pk": api_key.id}))
    linked = {row["internal_id"] for row in detail.data["linked_managed_nodes"]}
    assert linked == {str(node_a.internal_id), str(node_b.internal_id)}
    assert detail.data["nodes"] == []


@pytest.mark.django_db
def test_meshcore_create_requires_mc_pubkey(create_user, create_constellation):
    user = create_user()
    constellation = create_constellation(protocol=Protocol.MESHCORE, created_by=user)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        reverse("managed-nodes-list"),
        {
            "name": "bad",
            "constellation_id": constellation.id,
            "protocol": Protocol.MESHCORE,
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "mc_pubkey" in response.data
