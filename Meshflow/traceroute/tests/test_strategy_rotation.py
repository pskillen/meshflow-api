"""Tests for Redis-backed strategy LRU (locmem cache in tests)."""

from django.core.cache import cache

import pytest

import nodes.tests.conftest  # noqa: F401
from constellations.models import Constellation
from traceroute.strategy_rotation import (
    applicable_strategies,
    ordered_strategies_for_feeder,
    pick_strategy_for_feeder,
    record_strategy_run,
)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_pick_strategy_rotates_cold_cache(create_user, create_managed_node):
    user = create_user()
    c = Constellation.objects.create(name="C1", created_by=user)
    mn = create_managed_node(
        constellation=c,
        allow_auto_traceroute=True,
        default_location_latitude=55.0,
        default_location_longitude=-4.2,
        node_id=0xB0000001,
    )
    first = pick_strategy_for_feeder(mn)
    assert first in applicable_strategies(mn)
    record_strategy_run(mn, first)
    second = pick_strategy_for_feeder(mn)
    assert second in applicable_strategies(mn)
    assert second != first


@pytest.mark.django_db
def test_ordered_strategies_first_matches_pick(create_user, create_managed_node):
    user = create_user()
    c = Constellation.objects.create(name="C2", created_by=user)
    mn = create_managed_node(
        constellation=c,
        allow_auto_traceroute=True,
        default_location_latitude=55.0,
        default_location_longitude=-4.2,
        node_id=0xB0000002,
    )
    ordered = ordered_strategies_for_feeder(mn)
    assert ordered[0] == pick_strategy_for_feeder(mn)
    assert set(ordered) == set(applicable_strategies(mn))
    assert len(ordered) == len(applicable_strategies(mn))
