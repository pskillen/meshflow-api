"""Unit tests for single-feeder (v4) resolution."""

from django.utils import timezone

import pytest
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory

from common.feeder_auth import (
    FEEDER_NOT_LINKED,
    FEEDER_PROTOCOL_MISMATCH,
    SHARED_API_KEY,
    FeederResolutionError,
    FeederScopedPermission,
    resolve_single_feeder,
)
from common.protocol import Protocol
from nodes.models import NodeAuth

MC_PUBKEY = "ab" * 32


@pytest.mark.django_db
def test_single_link_resolves(create_managed_node, create_node_api_key):
    node = create_managed_node(protocol=Protocol.MESHTASTIC)
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)

    assert resolve_single_feeder(api_key) == node
    assert resolve_single_feeder(api_key, protocol=Protocol.MESHTASTIC) == node


@pytest.mark.django_db
def test_no_link_is_not_linked(create_node_api_key):
    api_key = create_node_api_key()

    with pytest.raises(FeederResolutionError) as exc:
        resolve_single_feeder(api_key)
    assert exc.value.code == FEEDER_NOT_LINKED


@pytest.mark.django_db
def test_only_deleted_link_is_not_linked(create_managed_node, create_node_api_key):
    node = create_managed_node(protocol=Protocol.MESHTASTIC, deleted_at=timezone.now())
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)

    with pytest.raises(FeederResolutionError) as exc:
        resolve_single_feeder(api_key)
    assert exc.value.code == FEEDER_NOT_LINKED


@pytest.mark.django_db
def test_two_links_is_shared_key(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHTASTIC)
    node_a = create_managed_node(
        protocol=Protocol.MESHTASTIC, constellation=constellation, name="A", meshtastic_node_id=1001
    )
    node_b = create_managed_node(
        protocol=Protocol.MESHTASTIC, constellation=constellation, name="B", meshtastic_node_id=1002
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node_a)
    NodeAuth.objects.create(api_key=api_key, node=node_b)

    with pytest.raises(FeederResolutionError) as exc:
        resolve_single_feeder(api_key)
    assert exc.value.code == SHARED_API_KEY
    assert "API keys page" in exc.value.detail
    assert "legacy" in exc.value.detail


@pytest.mark.django_db
def test_soft_deleted_second_link_still_resolves(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHTASTIC)
    live = create_managed_node(
        protocol=Protocol.MESHTASTIC, constellation=constellation, name="Live", meshtastic_node_id=2001
    )
    gone = create_managed_node(
        protocol=Protocol.MESHTASTIC,
        constellation=constellation,
        name="Gone",
        meshtastic_node_id=2002,
        deleted_at=timezone.now(),
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=live)
    NodeAuth.objects.create(api_key=api_key, node=gone)

    assert resolve_single_feeder(api_key) == live


@pytest.mark.django_db
def test_protocol_mismatch(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHCORE)
    node = create_managed_node(
        protocol=Protocol.MESHCORE,
        constellation=constellation,
        meshtastic_node_id=None,
        mc_pubkey=MC_PUBKEY,
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)

    assert resolve_single_feeder(api_key) == node
    with pytest.raises(FeederResolutionError) as exc:
        resolve_single_feeder(api_key, protocol=Protocol.MESHTASTIC)
    assert exc.value.code == FEEDER_PROTOCOL_MISMATCH


class _View:
    feeder_protocol = Protocol.MESHTASTIC


@pytest.mark.django_db
def test_permission_attaches_node(create_managed_node, create_node_api_key):
    node = create_managed_node(protocol=Protocol.MESHTASTIC)
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)
    request = APIRequestFactory().get("/")
    request.auth = api_key

    assert FeederScopedPermission().has_permission(request, _View()) is True
    assert request.auth.node == node


@pytest.mark.django_db
def test_permission_raises_coded_403(create_node_api_key):
    api_key = create_node_api_key()
    request = APIRequestFactory().get("/")
    request.auth = api_key

    with pytest.raises(PermissionDenied) as exc:
        FeederScopedPermission().has_permission(request, _View())
    assert exc.value.detail["code"] == FEEDER_NOT_LINKED
    assert exc.value.detail["detail"]
