"""Unit tests for mesh_monitoring.selection (monitoring traceroute sources)."""

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
from mesh_monitoring.selection import select_monitoring_sources
from nodes.models import NodeLatestStatus


@pytest.mark.django_db
def test_select_monitoring_sources_orders_by_distance(
    create_observed_node,
    create_managed_node,
    mark_managed_node_feeding,
):
    target = create_observed_node(node_id=0xE1000001)
    NodeLatestStatus.objects.create(node=target, latitude=48.0, longitude=2.0)

    far = create_managed_node(
        allow_auto_traceroute=True,
        node_id=0xE1000010,
        default_location_latitude=48.9,
        default_location_longitude=2.0,
    )
    near = create_managed_node(
        allow_auto_traceroute=True,
        node_id=0xE1000011,
        default_location_latitude=48.02,
        default_location_longitude=2.02,
    )
    mark_managed_node_feeding(far, sending=True)
    mark_managed_node_feeding(near, sending=True)

    picks = select_monitoring_sources(target, max_sources=3)
    assert [mn.node_id for mn in picks[:2]] == [near.node_id, far.node_id]


@pytest.mark.django_db
def test_select_monitoring_sources_excludes_managed_node_same_mesh_id_as_target(
    create_observed_node,
    create_managed_node,
    mark_managed_node_feeding,
):
    mesh_id = 0xE2000001
    target = create_observed_node(node_id=mesh_id)
    NodeLatestStatus.objects.create(node=target, latitude=50.0, longitude=0.0)

    same_radio = create_managed_node(
        allow_auto_traceroute=True,
        node_id=mesh_id,
        default_location_latitude=50.01,
        default_location_longitude=0.01,
    )
    helper = create_managed_node(
        allow_auto_traceroute=True,
        node_id=0xE2000099,
        default_location_latitude=50.5,
        default_location_longitude=0.5,
    )
    mark_managed_node_feeding(same_radio, sending=True)
    mark_managed_node_feeding(helper, sending=True)

    picks = select_monitoring_sources(target, max_sources=3)
    assert all(mn.node_id != mesh_id for mn in picks)
    assert picks[0].node_id == helper.node_id


@pytest.mark.django_db
def test_select_monitoring_sources_omits_non_feeding_managed_nodes(
    create_observed_node,
    create_managed_node,
    mark_managed_node_feeding,
):
    target = create_observed_node(node_id=0xE3000001)
    NodeLatestStatus.objects.create(node=target, latitude=51.0, longitude=1.0)

    stale = create_managed_node(
        allow_auto_traceroute=True,
        node_id=0xE3000010,
        default_location_latitude=51.01,
        default_location_longitude=1.01,
    )
    mark_managed_node_feeding(stale, sending=False)

    fresh = create_managed_node(
        allow_auto_traceroute=True,
        node_id=0xE3000011,
        default_location_latitude=51.02,
        default_location_longitude=1.02,
    )
    mark_managed_node_feeding(fresh, sending=True)

    picks = select_monitoring_sources(target, max_sources=3)
    assert picks == [fresh]


@pytest.mark.django_db
def test_select_monitoring_sources_respects_spacing_cooldown(
    create_observed_node,
    create_managed_node,
    mark_managed_node_feeding,
):
    from traceroute.models import AutoTraceRoute

    target = create_observed_node(node_id=0xE4000001)
    NodeLatestStatus.objects.create(node=target, latitude=49.0, longitude=1.5)

    mn = create_managed_node(
        allow_auto_traceroute=True,
        node_id=0xE4000010,
        default_location_latitude=49.01,
        default_location_longitude=1.51,
    )
    mark_managed_node_feeding(mn, sending=True)

    AutoTraceRoute.objects.create(
        source_node=mn,
        target_node=target,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_AUTO,
        status=AutoTraceRoute.STATUS_SENT,
        triggered_at=timezone.now(),
    )

    assert select_monitoring_sources(target, max_sources=3) == []
