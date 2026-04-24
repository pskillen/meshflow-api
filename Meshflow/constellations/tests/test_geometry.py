"""Tests for constellation geometry helpers."""

import pytest

import nodes.tests.conftest  # noqa: F401
from constellations.geometry import (
    _compute_envelope_circle,
    bearing_difference_deg,
    constellation_centroid,
    initial_bearing_deg,
    octant_from_bearing,
)
from constellations.models import Constellation


@pytest.mark.django_db
def test_constellation_centroid_mean(create_user, create_managed_node, mark_constellation_managed_nodes_feeding):
    user = create_user()
    c = Constellation.objects.create(name="G", created_by=user)
    create_managed_node(
        constellation=c,
        default_location_latitude=0.0,
        default_location_longitude=0.0,
        node_id=1,
    )
    create_managed_node(
        constellation=c,
        default_location_latitude=2.0,
        default_location_longitude=2.0,
        node_id=2,
    )
    mark_constellation_managed_nodes_feeding(c)
    cc = constellation_centroid(c)
    assert cc is not None
    assert abs(cc[0] - 1.0) < 1e-9
    assert abs(cc[1] - 1.0) < 1e-9


@pytest.mark.django_db
def test_envelope_circle_counts_only_actively_feeding_managed_nodes(
    create_user, create_managed_node, mark_managed_node_feeding
):
    user = create_user()
    c = Constellation.objects.create(name="Env", created_by=user)
    a = create_managed_node(
        constellation=c,
        default_location_latitude=55.0,
        default_location_longitude=-4.25,
        node_id=10,
    )
    b = create_managed_node(
        constellation=c,
        default_location_latitude=55.03,
        default_location_longitude=-4.25,
        node_id=11,
    )
    d = create_managed_node(
        constellation=c,
        default_location_latitude=55.02,
        default_location_longitude=-4.22,
        node_id=12,
    )
    mark_managed_node_feeding(a, sending=True)
    mark_managed_node_feeding(b, sending=True)
    assert _compute_envelope_circle(c) is None

    mark_managed_node_feeding(d, sending=True)
    env = _compute_envelope_circle(c)
    assert env is not None
    assert env["n_managed_positions"] == 3


def test_bearing_and_octant():
    b = initial_bearing_deg(55.0, -4.25, 55.1, -4.26)
    assert 0 <= b < 360
    assert octant_from_bearing(b) in ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    assert bearing_difference_deg(10, 350) <= 20
