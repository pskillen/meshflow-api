"""Tests for ``build_geo_classification`` (managed-node geo + selector preview fields)."""

from django.core.cache import cache

import pytest

import nodes.tests.conftest  # noqa: F401
from constellations.geometry import PERIMETER_DISTANCE_FRACTION
from traceroute.geo_classification import (
    DX_HALF_WINDOW_SWEEP_DEG,
    SELECTOR_LAST_HEARD_WITHIN_HOURS,
    build_geo_classification,
)


@pytest.fixture(autouse=True)
def _clear_constellation_envelope_cache():
    """Envelope is cached by constellation PK; reuse-db can recycle PKs with stale cache."""
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_geo_classification_envelope_and_selector_params_perimeter_feeder(
    create_user, create_managed_node, mark_constellation_managed_nodes_feeding
):
    user = create_user()
    c1 = create_managed_node(
        owner=user,
        node_id=1001,
        default_location_latitude=55.0,
        default_location_longitude=-4.25,
    ).constellation
    create_managed_node(
        owner=user,
        constellation=c1,
        node_id=1002,
        default_location_latitude=55.03,
        default_location_longitude=-4.25,
    )
    create_managed_node(
        owner=user,
        constellation=c1,
        node_id=1003,
        default_location_latitude=55.015,
        default_location_longitude=-4.22,
    )
    feeder = create_managed_node(
        owner=user,
        constellation=c1,
        node_id=1004,
        default_location_latitude=55.25,
        default_location_longitude=-4.25,
    )

    mark_constellation_managed_nodes_feeding(c1)
    geo = build_geo_classification(feeder)

    assert geo["tier"] == "perimeter"
    assert geo["envelope"] is not None
    assert set(geo["envelope"]) == {"centroid_lat", "centroid_lon", "radius_km"}
    assert geo["envelope"]["radius_km"] > 0
    assert geo["selection_centroid"] == {
        "lat": geo["envelope"]["centroid_lat"],
        "lon": geo["envelope"]["centroid_lon"],
    }
    assert geo["source_bearing_deg"] is not None
    assert 0 <= geo["source_bearing_deg"] < 360

    sp = geo["selector_params"]
    assert sp["last_heard_within_hours"] == SELECTOR_LAST_HEARD_WITHIN_HOURS
    assert sp["dx_half_window_sweep_deg"] == DX_HALF_WINDOW_SWEEP_DEG
    assert sp["perimeter_distance_fraction"] == PERIMETER_DISTANCE_FRACTION


@pytest.mark.django_db
def test_geo_classification_internal_feeder_still_has_envelope(
    create_user, create_managed_node, mark_constellation_managed_nodes_feeding
):
    user = create_user()
    c1 = create_managed_node(
        owner=user,
        node_id=2001,
        default_location_latitude=55.0,
        default_location_longitude=-4.25,
    ).constellation
    create_managed_node(
        owner=user,
        constellation=c1,
        node_id=2002,
        default_location_latitude=55.03,
        default_location_longitude=-4.25,
    )
    create_managed_node(
        owner=user,
        constellation=c1,
        node_id=2003,
        default_location_latitude=55.015,
        default_location_longitude=-4.22,
    )
    # Rough centroid of the three corners (~55.015, -4.24); place feeder there.
    feeder = create_managed_node(
        owner=user,
        constellation=c1,
        node_id=2004,
        default_location_latitude=55.015,
        default_location_longitude=-4.24,
    )

    mark_constellation_managed_nodes_feeding(c1)
    geo = build_geo_classification(feeder)
    assert geo["tier"] == "internal"
    assert geo["envelope"] is not None
    assert geo["source_bearing_deg"] is not None


@pytest.mark.django_db
def test_geo_classification_no_envelope_two_nodes_source_bearing_from_centroid(
    create_user, create_managed_node, mark_constellation_managed_nodes_feeding
):
    """Envelope needs ≥3 positioned managed nodes; centroid still exists for two."""
    user = create_user()
    c1 = create_managed_node(
        owner=user,
        node_id=3001,
        default_location_latitude=55.0,
        default_location_longitude=-4.25,
    ).constellation
    feeder = create_managed_node(
        owner=user,
        constellation=c1,
        node_id=3002,
        default_location_latitude=55.02,
        default_location_longitude=-4.25,
    )

    mark_constellation_managed_nodes_feeding(c1)
    geo = build_geo_classification(feeder)
    assert geo["envelope"] is None
    assert geo["selection_centroid"] is not None
    assert {"lat", "lon"} == set(geo["selection_centroid"])
    assert geo["source_bearing_deg"] is not None
    assert 0 <= geo["source_bearing_deg"] < 360
