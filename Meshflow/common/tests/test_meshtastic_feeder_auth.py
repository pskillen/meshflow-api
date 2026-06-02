"""Unit tests for Meshtastic feeder resolution."""

import pytest

from common.meshtastic_feeder_auth import (
    MeshtasticFeederResolutionError,
    resolve_meshtastic_feeder,
)
from common.protocol import Protocol
from nodes.models import NodeAuth

MT_NODE_A = 0x433B82F0
MT_NODE_B = 0x12345678


@pytest.mark.django_db
def test_resolve_single_feeder(create_managed_node, create_node_api_key):
    node = create_managed_node(meshtastic_node_id=MT_NODE_A, protocol=Protocol.MESHTASTIC)
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)

    assert (
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id=MT_NODE_A,
        )
        == node
    )


@pytest.mark.django_db
def test_resolve_by_node_id_str(create_managed_node, create_node_api_key):
    node = create_managed_node(meshtastic_node_id=MT_NODE_A, protocol=Protocol.MESHTASTIC)
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)

    assert (
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id_str="!433b82f0",
        )
        == node
    )


@pytest.mark.django_db
def test_resolve_wrong_node_id(create_managed_node, create_node_api_key):
    node = create_managed_node(meshtastic_node_id=MT_NODE_A, protocol=Protocol.MESHTASTIC)
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)

    with pytest.raises(MeshtasticFeederResolutionError) as exc:
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id=MT_NODE_B,
        )
    assert exc.value.code == "feeder_not_linked"


@pytest.mark.django_db
def test_shared_key_two_feeders(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHTASTIC)
    node_a = create_managed_node(
        meshtastic_node_id=MT_NODE_A,
        protocol=Protocol.MESHTASTIC,
        constellation=constellation,
        name="Feeder A",
    )
    node_b = create_managed_node(
        meshtastic_node_id=MT_NODE_B,
        protocol=Protocol.MESHTASTIC,
        constellation=constellation,
        name="Feeder B",
    )
    api_key = create_node_api_key(constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=node_a)
    NodeAuth.objects.create(api_key=api_key, node=node_b)

    assert (
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id=MT_NODE_A,
        )
        == node_a
    )
    assert (
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id=MT_NODE_B,
        )
        == node_b
    )


@pytest.mark.django_db
def test_missing_node_id(create_node_api_key, create_constellation):
    api_key = create_node_api_key(constellation=create_constellation(protocol=Protocol.MESHTASTIC))
    with pytest.raises(MeshtasticFeederResolutionError) as exc:
        resolve_meshtastic_feeder(api_key=api_key)
    assert exc.value.code == "missing_feeder_node_id"


@pytest.mark.django_db
def test_both_node_id_params_rejected(create_node_api_key, create_constellation):
    api_key = create_node_api_key(constellation=create_constellation(protocol=Protocol.MESHTASTIC))
    with pytest.raises(MeshtasticFeederResolutionError) as exc:
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id=MT_NODE_A,
            feeder_node_id_str="!433b82f0",
        )
    assert exc.value.code == "invalid_feeder_node_id"


@pytest.mark.django_db
def test_invalid_node_id_str(create_node_api_key, create_constellation):
    api_key = create_node_api_key(constellation=create_constellation(protocol=Protocol.MESHTASTIC))
    with pytest.raises(MeshtasticFeederResolutionError) as exc:
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id_str="not-a-node-id",
        )
    assert exc.value.code == "invalid_feeder_node_id_str"
