"""Unit tests for traceroute.feeder_ranges helpers."""

import pytest

import nodes.tests.conftest  # noqa: F401 - load fixtures
import users.tests.conftest  # noqa: F401 - load fixtures
from nodes.models import NodeLatestStatus
from traceroute.feeder_ranges import (
    DEFAULT_MIN_SAMPLES,
    _percentile,
    compute_feeder_ranges,
)
from traceroute.models import AutoTraceRoute


@pytest.fixture
def create_observed_with_position(create_observed_node):
    """Create an ObservedNode with a NodeLatestStatus position attached."""

    def _make(*, node_id: int, lat: float | None, lon: float | None, **kwargs):
        on = create_observed_node(node_id=node_id, **kwargs)
        if lat is not None and lon is not None:
            NodeLatestStatus.objects.create(node=on, latitude=lat, longitude=lon)
        return on

    return _make


@pytest.fixture
def make_completed_tr(create_auto_traceroute):
    """Create a completed AutoTraceRoute with explicit route legs."""

    def _make(*, source, target, route=None, route_back=None):
        return create_auto_traceroute(
            source_node=source,
            target_node=target,
            status=AutoTraceRoute.STATUS_COMPLETED,
            route=route,
            route_back=route_back,
        )

    return _make


# Glasgow centre as feeder anchor; targets ~5km / ~15km / ~30km away.
GLA_LAT = 55.8642
GLA_LON = -4.2518
NEAR_LAT = 55.8642  # ~5 km east
NEAR_LON = -4.1721
MID_LAT = 55.8642  # ~15 km east
MID_LON = -4.0127
FAR_LAT = 55.8642  # ~30 km east
FAR_LON = -3.7733


# ---------- Percentile helper ----------


def test_percentile_single_value():
    assert _percentile([7.5], 50) == 7.5
    assert _percentile([7.5], 95) == 7.5


def test_percentile_known_distribution():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert _percentile(values, 50) == pytest.approx(5.5)
    assert _percentile(values, 90) == pytest.approx(9.1)
    assert _percentile(values, 95) == pytest.approx(9.55)


def test_percentile_raises_on_empty():
    with pytest.raises(ValueError):
        _percentile([], 50)


# ---------- compute_feeder_ranges ----------


@pytest.mark.django_db
def test_empty_window_returns_empty_feeders():
    result = compute_feeder_ranges()
    assert result["feeders"] == []
    assert result["meta"]["min_samples"] == DEFAULT_MIN_SAMPLES


@pytest.mark.django_db
def test_single_sample_marked_low_confidence(create_managed_node, create_observed_with_position, make_completed_tr):
    feeder = create_managed_node(
        node_id=0x1111_1111,
        default_location_latitude=GLA_LAT,
        default_location_longitude=GLA_LON,
    )
    target = create_observed_with_position(node_id=0x2222_2222, lat=NEAR_LAT, lon=NEAR_LON)
    make_completed_tr(source=feeder, target=target)

    result = compute_feeder_ranges(min_samples=10)
    assert len(result["feeders"]) == 1
    feeder_out = result["feeders"][0]
    assert feeder_out["any"]["sample_count"] == 1
    assert feeder_out["any"]["low_confidence"] is True
    assert feeder_out["direct"]["sample_count"] == 1
    assert feeder_out["any"]["p95_km"] == pytest.approx(5.0, abs=0.2)


@pytest.mark.django_db
def test_drops_rows_with_missing_target_position(
    create_managed_node, create_observed_node, create_observed_with_position, make_completed_tr
):
    feeder = create_managed_node(
        node_id=0x1111_1111,
        default_location_latitude=GLA_LAT,
        default_location_longitude=GLA_LON,
    )
    target_with_pos = create_observed_with_position(node_id=0x2222_2222, lat=NEAR_LAT, lon=NEAR_LON)
    target_no_pos = create_observed_node(node_id=0x3333_3333)
    make_completed_tr(source=feeder, target=target_with_pos)
    make_completed_tr(source=feeder, target=target_no_pos)

    result = compute_feeder_ranges()
    assert len(result["feeders"]) == 1
    assert result["feeders"][0]["any"]["sample_count"] == 1


@pytest.mark.django_db
def test_drops_feeder_without_position(create_managed_node, create_observed_with_position, make_completed_tr):
    # No default_location_*, no NodeLatestStatus -> feeder has no resolvable position.
    feeder = create_managed_node(node_id=0x1111_1111)
    target = create_observed_with_position(node_id=0x2222_2222, lat=NEAR_LAT, lon=NEAR_LON)
    make_completed_tr(source=feeder, target=target)

    result = compute_feeder_ranges()
    assert result["feeders"] == []


@pytest.mark.django_db
def test_direct_vs_any_partitioning(create_managed_node, create_observed_with_position, make_completed_tr):
    feeder = create_managed_node(
        node_id=0x1111_1111,
        default_location_latitude=GLA_LAT,
        default_location_longitude=GLA_LON,
    )
    near = create_observed_with_position(node_id=0x2222_2222, lat=NEAR_LAT, lon=NEAR_LON)
    far = create_observed_with_position(node_id=0x3333_3333, lat=FAR_LAT, lon=FAR_LON)
    # Direct hop to near
    make_completed_tr(source=feeder, target=near, route=[], route_back=[])
    # Multi-hop to far (via a relay)
    make_completed_tr(
        source=feeder,
        target=far,
        route=[{"node_id": 0x4444_4444, "snr": 6.0}],
        route_back=[{"node_id": 0x4444_4444, "snr": 5.5}],
    )

    result = compute_feeder_ranges(min_samples=1)
    feeder_out = result["feeders"][0]
    assert feeder_out["direct"]["sample_count"] == 1
    assert feeder_out["any"]["sample_count"] == 2
    # Any-mode max should reflect the far target.
    assert feeder_out["any"]["max_km"] > feeder_out["direct"]["max_km"]


@pytest.mark.django_db
def test_known_distribution_percentiles(create_managed_node, create_observed_with_position, make_completed_tr):
    feeder = create_managed_node(
        node_id=0x1111_1111,
        default_location_latitude=GLA_LAT,
        default_location_longitude=GLA_LON,
    )
    near = create_observed_with_position(node_id=0x2222_2222, lat=NEAR_LAT, lon=NEAR_LON)  # ~5 km
    mid = create_observed_with_position(node_id=0x3333_3333, lat=MID_LAT, lon=MID_LON)  # ~15 km
    far = create_observed_with_position(node_id=0x4444_4444, lat=FAR_LAT, lon=FAR_LON)  # ~30 km

    # 8 near + 1 mid + 1 far -> p50 ~ 5km, max ~ 30km, sample_count = 10
    for _ in range(8):
        make_completed_tr(source=feeder, target=near)
    make_completed_tr(source=feeder, target=mid)
    make_completed_tr(source=feeder, target=far)

    result = compute_feeder_ranges(min_samples=10)
    block = result["feeders"][0]["any"]
    assert block["sample_count"] == 10
    assert block["low_confidence"] is False
    assert block["p50_km"] == pytest.approx(5.0, abs=0.2)
    assert block["max_km"] == pytest.approx(30.0, abs=0.5)


@pytest.mark.django_db
def test_min_samples_override_flips_low_confidence(
    create_managed_node, create_observed_with_position, make_completed_tr
):
    feeder = create_managed_node(
        node_id=0x1111_1111,
        default_location_latitude=GLA_LAT,
        default_location_longitude=GLA_LON,
    )
    target = create_observed_with_position(node_id=0x2222_2222, lat=NEAR_LAT, lon=NEAR_LON)
    for _ in range(3):
        make_completed_tr(source=feeder, target=target)

    high = compute_feeder_ranges(min_samples=10)
    low = compute_feeder_ranges(min_samples=2)
    assert high["feeders"][0]["any"]["low_confidence"] is True
    assert low["feeders"][0]["any"]["low_confidence"] is False


@pytest.mark.django_db
def test_only_completed_traceroutes_counted(create_managed_node, create_observed_with_position, create_auto_traceroute):
    feeder = create_managed_node(
        node_id=0x1111_1111,
        default_location_latitude=GLA_LAT,
        default_location_longitude=GLA_LON,
    )
    target = create_observed_with_position(node_id=0x2222_2222, lat=NEAR_LAT, lon=NEAR_LON)
    create_auto_traceroute(source_node=feeder, target_node=target, status=AutoTraceRoute.STATUS_FAILED)
    create_auto_traceroute(source_node=feeder, target_node=target, status=AutoTraceRoute.STATUS_PENDING)

    result = compute_feeder_ranges()
    assert result["feeders"] == []
