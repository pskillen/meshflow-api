"""Target selection excludes mesh IDs that belong to any ManagedNode."""

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import NodeLatestStatus
from traceroute.target_selection import pick_traceroute_target


@pytest.mark.django_db
def test_pick_traceroute_target_excludes_observed_node_whose_mesh_id_is_managed(
    create_managed_node,
    create_observed_node,
):
    """Any ObservedNode whose node_id matches a ManagedNode cannot be an auto target."""
    source = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=51.0,
        default_location_longitude=-0.1,
        node_id=0xD1000001,
    )
    other_mn = create_managed_node(node_id=0xD1000002)
    on_mesh_id = other_mn.node_id
    victim = create_observed_node(
        node_id=on_mesh_id,
        node_id_str=meshtastic_id_to_hex(on_mesh_id),
        last_heard=timezone.now(),
    )
    NodeLatestStatus.objects.create(node=victim, latitude=51.01, longitude=-0.11)

    free = create_observed_node(
        node_id=0xD1000099,
        node_id_str=meshtastic_id_to_hex(0xD1000099),
        last_heard=timezone.now(),
    )
    NodeLatestStatus.objects.create(node=free, latitude=51.02, longitude=-0.12)

    picked = pick_traceroute_target(source)
    assert picked is not None
    assert picked.node_id != victim.node_id
    assert picked.node_id == free.node_id


@pytest.mark.django_db
def test_managed_node_mesh_id_excluded_even_without_managednodestatus_row(create_managed_node, create_observed_node):
    """Placeholder managed nodes still occupy their mesh ID in the exclusion set."""
    source = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=52.0,
        default_location_longitude=1.0,
        node_id=0xD2000001,
    )
    create_managed_node(node_id=0xD2000002)

    victim = create_observed_node(
        node_id=0xD2000002,
        node_id_str=meshtastic_id_to_hex(0xD2000002),
        last_heard=timezone.now(),
    )
    NodeLatestStatus.objects.create(node=victim, latitude=52.01, longitude=1.01)

    free = create_observed_node(
        node_id=0xD2000099,
        node_id_str=meshtastic_id_to_hex(0xD2000099),
        last_heard=timezone.now(),
    )
    NodeLatestStatus.objects.create(node=free, latitude=52.02, longitude=1.02)

    picked = pick_traceroute_target(source)
    assert picked is not None
    assert picked.node_id == free.node_id
