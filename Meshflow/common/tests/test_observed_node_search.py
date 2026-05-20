"""Tests for ObservedNode search Q builder."""

import pytest

from common.mesh_node_helpers import observed_node_search_conditions
from common.protocol import Protocol
from nodes.models import ObservedNode

FULL_PUBKEY = "b" * 64
PREFIX = "b" * 12


@pytest.mark.django_db
def test_search_meshtastic_hex_exact(create_observed_node):
    node = create_observed_node(meshtastic_node_id=0x12345678)
    qs = ObservedNode.objects.filter(observed_node_search_conditions("!12345678"))
    assert node in qs


@pytest.mark.django_db
def test_search_meshcore_display_prefix(create_observed_node):
    node = create_observed_node(
        protocol=Protocol.MESHCORE,
        meshtastic_node_id=None,
        mc_pubkey=FULL_PUBKEY,
        mc_pubkey_prefix=PREFIX,
        long_name="MC node",
        short_name="MC",
    )
    qs = ObservedNode.objects.filter(observed_node_search_conditions(f"mc:{PREFIX}"))
    assert node in qs


@pytest.mark.django_db
def test_search_by_short_name(create_observed_node):
    node = create_observed_node(short_name="ZZTOP")
    qs = ObservedNode.objects.filter(observed_node_search_conditions("ZZTOP"))
    assert node in qs
