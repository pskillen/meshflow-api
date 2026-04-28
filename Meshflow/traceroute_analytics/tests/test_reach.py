"""Unit tests for the per-(feeder, target) reach helper."""

from datetime import timedelta

from django.utils import timezone

import pytest

from nodes.models import NodeLatestStatus
from traceroute.models import AutoTraceRoute
from traceroute_analytics.reach import compute_reach

pytestmark = pytest.mark.django_db


def test_attempts_count_completed_and_failed_only(create_managed_node, create_observed_node, create_auto_traceroute):
    feeder = create_managed_node(
        node_id=0xF11D_E001,
        default_location_latitude=55.86,
        default_location_longitude=-4.25,
    )
    target = create_observed_node(node_id=0x7777_0001)
    NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)

    for _ in range(4):
        create_auto_traceroute(
            source_node=feeder,
            target_node=target,
            status=AutoTraceRoute.STATUS_COMPLETED,
        )
    for _ in range(2):
        create_auto_traceroute(
            source_node=feeder,
            target_node=target,
            status=AutoTraceRoute.STATUS_FAILED,
        )
    create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_PENDING,
    )
    create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_SENT,
    )

    rows = compute_reach()
    assert len(rows) == 1
    row = rows[0]
    assert row.attempts == 6
    assert row.successes == 4


def test_drops_targets_without_position(create_managed_node, create_observed_node, create_auto_traceroute):
    feeder = create_managed_node(
        node_id=0xF11D_E002,
        default_location_latitude=55.86,
        default_location_longitude=-4.25,
    )
    target = create_observed_node(node_id=0x7777_0002)
    create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_COMPLETED,
    )

    assert compute_reach() == []


def test_drops_feeders_without_position(create_managed_node, create_observed_node, create_auto_traceroute):
    feeder = create_managed_node(node_id=0xF11D_E003)
    target = create_observed_node(node_id=0x7777_0003)
    NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)

    create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_COMPLETED,
    )

    assert compute_reach() == []


def test_groups_by_feeder_target_pair(create_managed_node, create_observed_node, create_auto_traceroute):
    feeder_a = create_managed_node(
        node_id=0xF11D_E004,
        default_location_latitude=55.86,
        default_location_longitude=-4.25,
    )
    feeder_b = create_managed_node(
        node_id=0xF11D_E005,
        default_location_latitude=55.95,
        default_location_longitude=-3.20,
    )
    target_x = create_observed_node(node_id=0x7777_0004)
    target_y = create_observed_node(node_id=0x7777_0005)
    NodeLatestStatus.objects.create(node=target_x, latitude=55.86, longitude=-4.20)
    NodeLatestStatus.objects.create(node=target_y, latitude=56.00, longitude=-3.00)

    create_auto_traceroute(
        source_node=feeder_a,
        target_node=target_x,
        status=AutoTraceRoute.STATUS_COMPLETED,
    )
    create_auto_traceroute(
        source_node=feeder_a,
        target_node=target_y,
        status=AutoTraceRoute.STATUS_FAILED,
    )
    create_auto_traceroute(
        source_node=feeder_b,
        target_node=target_x,
        status=AutoTraceRoute.STATUS_COMPLETED,
    )

    rows = compute_reach()
    pairs = {(r.feeder_node_id, r.target_node_id): (r.attempts, r.successes) for r in rows}
    assert pairs == {
        (feeder_a.node_id, target_x.node_id): (1, 1),
        (feeder_a.node_id, target_y.node_id): (1, 0),
        (feeder_b.node_id, target_x.node_id): (1, 1),
    }


def test_feeder_id_filter(create_managed_node, create_observed_node, create_auto_traceroute):
    feeder_keep = create_managed_node(
        node_id=0xF11D_E006,
        default_location_latitude=55.86,
        default_location_longitude=-4.25,
    )
    feeder_drop = create_managed_node(
        node_id=0xF11D_E007,
        default_location_latitude=55.95,
        default_location_longitude=-3.20,
    )
    target = create_observed_node(node_id=0x7777_0006)
    NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)

    for f in (feeder_keep, feeder_drop):
        create_auto_traceroute(
            source_node=f,
            target_node=target,
            status=AutoTraceRoute.STATUS_COMPLETED,
        )

    rows = compute_reach(feeder_id=feeder_keep.node_id)
    assert {r.feeder_node_id for r in rows} == {feeder_keep.node_id}


def test_constellation_filter(
    create_managed_node,
    create_observed_node,
    create_auto_traceroute,
    create_constellation,
    create_user,
):
    owner = create_user()
    constellation_keep = create_constellation(created_by=owner)
    constellation_drop = create_constellation(created_by=owner)

    feeder_keep = create_managed_node(
        owner=owner,
        constellation=constellation_keep,
        node_id=0xF11D_E008,
        default_location_latitude=55.86,
        default_location_longitude=-4.25,
    )
    feeder_drop = create_managed_node(
        owner=owner,
        constellation=constellation_drop,
        node_id=0xF11D_E009,
        default_location_latitude=55.95,
        default_location_longitude=-3.20,
    )
    target = create_observed_node(node_id=0x7777_0007)
    NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)

    for f in (feeder_keep, feeder_drop):
        create_auto_traceroute(
            source_node=f,
            target_node=target,
            status=AutoTraceRoute.STATUS_COMPLETED,
        )

    rows = compute_reach(constellation_id=constellation_keep.id)
    assert {r.feeder_node_id for r in rows} == {feeder_keep.node_id}


def test_window_filter(create_managed_node, create_observed_node, create_auto_traceroute):
    feeder = create_managed_node(
        node_id=0xF11D_E00A,
        default_location_latitude=55.86,
        default_location_longitude=-4.25,
    )
    target = create_observed_node(node_id=0x7777_0008)
    NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)

    now = timezone.now()
    fresh = create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_COMPLETED,
    )
    fresh.triggered_at = now - timedelta(hours=1)
    fresh.save(update_fields=["triggered_at"])

    stale = create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_COMPLETED,
    )
    stale.triggered_at = now - timedelta(days=10)
    stale.save(update_fields=["triggered_at"])

    rows = compute_reach(triggered_at_after=now - timedelta(days=1))
    assert len(rows) == 1
    assert rows[0].attempts == 1
    assert rows[0].successes == 1


def test_target_strategy_tokens_filter(create_managed_node, create_observed_node, create_auto_traceroute):
    feeder = create_managed_node(
        node_id=0xF11D_E00C,
        default_location_latitude=55.86,
        default_location_longitude=-4.25,
    )
    target = create_observed_node(node_id=0x7777_000A)
    NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)

    create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_COMPLETED,
        target_strategy=AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE,
    )
    create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_COMPLETED,
        target_strategy=AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS,
    )

    rows_all = compute_reach(feeder_id=feeder.node_id)
    assert rows_all[0].attempts == 2

    rows_intra = compute_reach(
        feeder_id=feeder.node_id,
        target_strategy_tokens=["intra_zone"],
    )
    assert len(rows_intra) == 1
    assert rows_intra[0].attempts == 1


def test_target_strategy_legacy_matches_null(create_managed_node, create_observed_node, create_auto_traceroute):
    feeder = create_managed_node(
        node_id=0xF11D_E00D,
        default_location_latitude=55.86,
        default_location_longitude=-4.25,
    )
    target = create_observed_node(node_id=0x7777_000B)
    NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)

    create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_COMPLETED,
        target_strategy=None,
    )
    create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_COMPLETED,
        target_strategy=AutoTraceRoute.TARGET_STRATEGY_LEGACY,
    )
    create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_COMPLETED,
        target_strategy=AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE,
    )

    rows = compute_reach(feeder_id=feeder.node_id, target_strategy_tokens=["legacy"])
    assert len(rows) == 1
    assert rows[0].attempts == 2


def test_emits_display_metadata(create_managed_node, create_observed_node, create_auto_traceroute):
    feeder = create_managed_node(
        node_id=0xF11D_E00B,
        name="Feeder MN",
        default_location_latitude=55.86,
        default_location_longitude=-4.25,
    )
    create_observed_node(node_id=feeder.node_id, short_name="FEEDR", long_name="Feeder long")
    target = create_observed_node(node_id=0x7777_0009, short_name="TGT1", long_name="Target One")
    NodeLatestStatus.objects.create(node=target, latitude=55.86, longitude=-4.20)

    create_auto_traceroute(
        source_node=feeder,
        target_node=target,
        status=AutoTraceRoute.STATUS_COMPLETED,
    )

    rows = compute_reach()
    assert len(rows) == 1
    row = rows[0]
    assert row.feeder_short_name == "FEEDR"
    assert row.feeder_long_name == "Feeder long"
    assert row.target_short_name == "TGT1"
    assert row.target_long_name == "Target One"
    assert row.feeder_node_id_str
    assert row.target_node_id_str
