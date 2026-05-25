"""Tests for observed node detail path lookup resolution."""

import pytest

from common.observed_node_lookup import (
    ObservedNodeLookupAmbiguous,
    ObservedNodeLookupNotFound,
    ObservedNodeLookupResolved,
    resolve_observed_node_lookup,
)
from common.protocol import Protocol

FULL_PUBKEY = "a" * 12 + "b" * 52
PREFIX = "a" * 12


@pytest.mark.django_db
def test_lookup_uuid(create_observed_node):
    node = create_observed_node(meshtastic_node_id=0x11111111)
    result = resolve_observed_node_lookup(str(node.internal_id))
    assert isinstance(result, ObservedNodeLookupResolved)
    assert result.node.pk == node.pk


@pytest.mark.django_db
def test_lookup_meshtastic_bang_hex(create_observed_node):
    node = create_observed_node(meshtastic_node_id=0x12345678)
    result = resolve_observed_node_lookup("!12345678")
    assert isinstance(result, ObservedNodeLookupResolved)
    assert result.node.pk == node.pk


@pytest.mark.django_db
def test_lookup_meshtastic_mt_prefix(create_observed_node):
    node = create_observed_node(meshtastic_node_id=0x12345678)
    result = resolve_observed_node_lookup("mt:12345678")
    assert isinstance(result, ObservedNodeLookupResolved)
    assert result.node.pk == node.pk


@pytest.mark.django_db
def test_lookup_meshcore_mc_prefix(create_observed_node):
    node = create_observed_node(
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey=FULL_PUBKEY,
        mc_pubkey_prefix=PREFIX,
        long_name="MC",
        short_name="MC",
    )
    result = resolve_observed_node_lookup(f"mc:{PREFIX}")
    assert isinstance(result, ObservedNodeLookupResolved)
    assert result.node.pk == node.pk


@pytest.mark.django_db
def test_lookup_bare_hex_meshtastic_only(create_observed_node):
    node = create_observed_node(meshtastic_node_id=0xABCDEF01)
    result = resolve_observed_node_lookup("abcdef01")
    assert isinstance(result, ObservedNodeLookupResolved)
    assert result.node.pk == node.pk


@pytest.mark.django_db
def test_lookup_bare_hex_ambiguous(create_observed_node):
    hex8 = "3ade68b1"
    mt = create_observed_node(meshtastic_node_id=int(hex8, 16))
    mc = create_observed_node(
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey_prefix=hex8 + "cafebabe",
        mc_pubkey=hex8 + "cafebabe" + "0" * 48,
        long_name="MC amb",
        short_name="AMB",
    )
    result = resolve_observed_node_lookup(hex8)
    assert isinstance(result, ObservedNodeLookupAmbiguous)
    pks = {n.pk for n in result.choices}
    assert mt.pk in pks
    assert mc.pk in pks


@pytest.mark.django_db
def test_lookup_not_found():
    result = resolve_observed_node_lookup("mc:" + "f" * 12)
    assert isinstance(result, ObservedNodeLookupNotFound)


@pytest.mark.django_db
def test_lookup_unknown_token():
    result = resolve_observed_node_lookup("not-a-node-id")
    assert isinstance(result, ObservedNodeLookupNotFound)
