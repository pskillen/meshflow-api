"""Unit tests for Meshtastic feeder resolution."""

import pytest

from common.meshtastic_feeder_auth import (
    MeshtasticFeederResolutionError,
    resolve_meshtastic_feeder,
)
from common.protocol import Protocol
from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import NodeAuth


@pytest.mark.django_db
def test_resolve_single_feeder(create_managed_node, create_node_api_key):
    node = create_managed_node(protocol=Protocol.MESHTASTIC)
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)

    assert (
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id=node.meshtastic_node_id,
        )
        == node
    )


@pytest.mark.django_db
def test_resolve_by_node_id_str(create_managed_node, create_node_api_key):
    node = create_managed_node(protocol=Protocol.MESHTASTIC)
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)

    assert (
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id_str=meshtastic_id_to_hex(node.meshtastic_node_id),
        )
        == node
    )


@pytest.mark.django_db
def test_resolve_wrong_node_id(create_managed_node, create_node_api_key):
    node = create_managed_node(protocol=Protocol.MESHTASTIC)
    other = create_managed_node(protocol=Protocol.MESHTASTIC)
    api_key = create_node_api_key(constellation=node.constellation)
    NodeAuth.objects.create(api_key=api_key, node=node)

    with pytest.raises(MeshtasticFeederResolutionError) as exc:
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id=other.meshtastic_node_id,
        )
    assert exc.value.code == "feeder_not_linked"


@pytest.mark.django_db
def test_shared_key_two_feeders(create_managed_node, create_constellation, create_node_api_key):
    constellation = create_constellation(protocol=Protocol.MESHTASTIC)
    node_a = create_managed_node(
        protocol=Protocol.MESHTASTIC,
        constellation=constellation,
        name="Feeder A",
    )
    node_b = create_managed_node(
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
            feeder_node_id=node_a.meshtastic_node_id,
        )
        == node_a
    )
    assert (
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id=node_b.meshtastic_node_id,
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
def test_both_node_id_params_rejected(create_managed_node, create_node_api_key):
    node = create_managed_node(protocol=Protocol.MESHTASTIC)
    api_key = create_node_api_key(constellation=node.constellation)
    with pytest.raises(MeshtasticFeederResolutionError) as exc:
        resolve_meshtastic_feeder(
            api_key=api_key,
            feeder_node_id=node.meshtastic_node_id,
            feeder_node_id_str=meshtastic_id_to_hex(node.meshtastic_node_id),
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
