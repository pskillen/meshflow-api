"""Tests for MeshCore node identity helpers."""

from django.utils import timezone

import pytest

from common.meshcore_node_helpers import (
    mc_node_id_str,
    merge_prefix_stub_into_full,
    normalize_mc_pubkey,
    pubkey_to_prefix,
    resolve_or_create_mc_observed_node,
)
from common.protocol import Protocol
from nodes.models import ObservedNode

FULL_PUBKEY = "a" * 64
PREFIX = "a" * 12


@pytest.mark.django_db
def test_normalize_mc_pubkey():
    assert normalize_mc_pubkey("AA" + "b" * 62) == "aa" + "b" * 62


def test_mc_node_id_str_from_pubkey():
    assert mc_node_id_str(mc_pubkey=FULL_PUBKEY) == f"mc:{PREFIX}"


@pytest.mark.django_db
def test_resolve_full_pubkey_creates_node():
    now = timezone.now()
    node = resolve_or_create_mc_observed_node(mc_pubkey=FULL_PUBKEY, last_heard=now)
    assert node.protocol == Protocol.MESHCORE
    assert node.mc_pubkey == FULL_PUBKEY
    assert node.mc_pubkey_prefix == PREFIX
    assert node.node_id_str == f"mc:{PREFIX}"
    assert node.last_heard == now


@pytest.mark.django_db
def test_prefix_stub_then_full_pubkey_merge():
    stub = resolve_or_create_mc_observed_node(mc_pubkey_prefix=PREFIX)
    assert stub.mc_pubkey is None
    assert ObservedNode.objects.filter(protocol=Protocol.MESHCORE).count() == 1

    full = resolve_or_create_mc_observed_node(mc_pubkey=FULL_PUBKEY)
    assert full.mc_pubkey == FULL_PUBKEY
    assert ObservedNode.objects.filter(protocol=Protocol.MESHCORE).count() == 1
    assert not ObservedNode.objects.filter(pk=stub.pk).exists()


@pytest.mark.django_db
def test_prefix_unique_match_updates_last_heard():
    full = resolve_or_create_mc_observed_node(mc_pubkey=FULL_PUBKEY)
    t1 = timezone.now()
    t2 = timezone.now()
    updated = resolve_or_create_mc_observed_node(mc_pubkey_prefix=PREFIX, last_heard=t2)
    assert updated.pk == full.pk
    assert updated.last_heard == t2


@pytest.mark.django_db
def test_merge_prefix_stub_into_full():
    stub = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey_prefix=PREFIX,
        node_id_str=mc_node_id_str(mc_pubkey_prefix=PREFIX),
        long_name="stub",
        short_name="stub",
    )
    full = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey=FULL_PUBKEY,
        mc_pubkey_prefix=PREFIX,
        node_id_str=mc_node_id_str(mc_pubkey=FULL_PUBKEY),
        long_name="full",
        short_name="full",
    )
    merge_prefix_stub_into_full(full)
    assert not ObservedNode.objects.filter(pk=stub.pk).exists()
