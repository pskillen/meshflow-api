"""Unit tests for MeshCore feeder resolution."""

import pytest

from common.meshcore_feeder_auth import MeshCoreFeederResolutionError, resolve_meshcore_feeder
from common.protocol import Protocol
from meshcore_packets.tests.conftest import (
    FEEDER_B_MC_PUBKEY,
    FEEDER_B_MC_PUBKEY_PREFIX,
    FEEDER_MC_PUBKEY,
    FEEDER_MC_PUBKEY_PREFIX,
)
from nodes.models import NodeAuth


@pytest.mark.django_db
def test_resolve_single_feeder(meshcore_feeder):
    node = resolve_meshcore_feeder(
        api_key=meshcore_feeder["api_key"],
        feeder_pubkey_prefix=FEEDER_MC_PUBKEY_PREFIX,
        feeder_pubkey_full=FEEDER_MC_PUBKEY,
    )
    assert node == meshcore_feeder["node"]


@pytest.mark.django_db
def test_resolve_wrong_prefix(meshcore_feeder):
    with pytest.raises(MeshCoreFeederResolutionError) as exc:
        resolve_meshcore_feeder(
            api_key=meshcore_feeder["api_key"],
            feeder_pubkey_prefix="deadbeef0000",
        )
    assert exc.value.code == "feeder_not_linked"


@pytest.mark.django_db
def test_resolve_pubkey_mismatch(meshcore_feeder):
    with pytest.raises(MeshCoreFeederResolutionError) as exc:
        resolve_meshcore_feeder(
            api_key=meshcore_feeder["api_key"],
            feeder_pubkey_prefix=FEEDER_MC_PUBKEY_PREFIX,
            feeder_pubkey_full="b" * 64,
        )
    assert exc.value.code == "feeder_pubkey_mismatch"


@pytest.mark.django_db
def test_shared_key_two_feeders(create_managed_node, create_node_api_key):
    constellation = create_managed_node(protocol=Protocol.MESHCORE).constellation
    node_a = create_managed_node(
        meshtastic_node_id=0,
        protocol=Protocol.MESHCORE,
        constellation=constellation,
        name="Feeder A",
        mc_pubkey=FEEDER_MC_PUBKEY,
    )
    node_b = create_managed_node(
        meshtastic_node_id=0,
        protocol=Protocol.MESHCORE,
        constellation=constellation,
        name="Feeder B",
        mc_pubkey=FEEDER_B_MC_PUBKEY,
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node_a)
    NodeAuth.objects.create(api_key=api_key, node=node_b)

    assert (
        resolve_meshcore_feeder(
            api_key=api_key,
            feeder_pubkey_prefix=FEEDER_MC_PUBKEY_PREFIX,
        )
        == node_a
    )
    assert (
        resolve_meshcore_feeder(
            api_key=api_key,
            feeder_pubkey_prefix=FEEDER_B_MC_PUBKEY_PREFIX,
        )
        == node_b
    )


@pytest.mark.django_db
def test_shared_key_missing_mc_pubkey(create_managed_node, create_node_api_key):
    constellation = create_managed_node(protocol=Protocol.MESHCORE).constellation
    node_a = create_managed_node(
        meshtastic_node_id=0,
        protocol=Protocol.MESHCORE,
        constellation=constellation,
        mc_pubkey=FEEDER_MC_PUBKEY,
    )
    node_b = create_managed_node(
        meshtastic_node_id=0,
        protocol=Protocol.MESHCORE,
        constellation=constellation,
        mc_pubkey=None,
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node_a)
    NodeAuth.objects.create(api_key=api_key, node=node_b)

    with pytest.raises(MeshCoreFeederResolutionError) as exc:
        resolve_meshcore_feeder(
            api_key=api_key,
            feeder_pubkey_prefix=FEEDER_MC_PUBKEY_PREFIX,
        )
    assert exc.value.code == "feeder_pubkey_not_configured"
