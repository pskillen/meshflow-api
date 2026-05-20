"""Tests for protocol-aware ObservedNode display id (ADR-0001)."""

import pytest

from common.mesh_node_helpers import observed_node_id_str
from common.protocol import Protocol
from nodes.models import ObservedNode

FULL_PUBKEY = "a" * 64
PREFIX = "a" * 12


@pytest.mark.django_db
def test_observed_node_id_str_meshtastic():
    node = ObservedNode.objects.create(
        protocol=Protocol.MESHTASTIC,
        meshtastic_node_id=987654321,
        long_name="MT",
        short_name="MT",
    )
    assert observed_node_id_str(node) == "!3ade68b1"


@pytest.mark.django_db
def test_observed_node_id_str_meshcore_full_pubkey():
    node = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey=FULL_PUBKEY,
        mc_pubkey_prefix=PREFIX,
        long_name="MC",
        short_name="MC",
    )
    assert observed_node_id_str(node) == f"mc:{PREFIX}"


@pytest.mark.django_db
def test_observed_node_id_str_meshcore_prefix_stub():
    node = ObservedNode.objects.create(
        protocol=Protocol.MESHCORE,
        mc_pubkey_prefix=PREFIX,
        long_name="stub",
        short_name="stub",
    )
    assert observed_node_id_str(node) == f"mc:{PREFIX}"
