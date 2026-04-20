"""Unit tests for :mod:`rf_propagation.bounds`."""

from __future__ import annotations

import math

import pytest

from rf_propagation.bounds import METRES_PER_DEGREE_LATITUDE, bbox_from_center


def test_bbox_equator_is_symmetric_in_lat_and_lng():
    radius_m = 20_000
    bbox = bbox_from_center(0.0, 0.0, radius_m)

    expected_deg = radius_m / METRES_PER_DEGREE_LATITUDE
    assert bbox.south == pytest.approx(-expected_deg)
    assert bbox.north == pytest.approx(expected_deg)
    # cos(0) == 1, so east/west deltas equal north/south at the equator.
    assert bbox.west == pytest.approx(-expected_deg)
    assert bbox.east == pytest.approx(expected_deg)


def test_bbox_is_wider_in_longitude_at_high_latitude():
    radius_m = 20_000
    lat = 60.0
    bbox = bbox_from_center(lat, 0.0, radius_m)

    d_lat = radius_m / METRES_PER_DEGREE_LATITUDE
    d_lng = radius_m / (METRES_PER_DEGREE_LATITUDE * math.cos(math.radians(lat)))

    assert bbox.north - bbox.south == pytest.approx(2 * d_lat)
    assert bbox.east - bbox.west == pytest.approx(2 * d_lng)
    # Longitude delta at 60°N is ~2x latitude delta because cos(60°)==0.5.
    assert (bbox.east - bbox.west) > (bbox.north - bbox.south)


def test_bbox_rejects_invalid_input():
    with pytest.raises(ValueError):
        bbox_from_center(0.0, 0.0, 0)
    with pytest.raises(ValueError):
        bbox_from_center(0.0, 0.0, -1)
    with pytest.raises(ValueError):
        bbox_from_center(95.0, 0.0, 1000)
    with pytest.raises(ValueError):
        bbox_from_center(0.0, 200.0, 1000)


def test_bbox_near_pole_uses_clamped_cosine():
    bbox = bbox_from_center(89.9999, 0.0, 1000)
    # Must not raise ZeroDivisionError; east/west are huge but finite.
    assert math.isfinite(bbox.east)
    assert math.isfinite(bbox.west)
