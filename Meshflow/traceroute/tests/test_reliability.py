"""Automatic traceroute target reliability (meshflow-api#211)."""

from datetime import timedelta

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import NodeLatestStatus
from traceroute.models import AutoTraceRoute
from traceroute.reliability import get_reliability_settings, load_source_target_reliability
from traceroute.target_selection import pick_traceroute_target


@pytest.mark.django_db
def test_load_reliability_hard_cooldown_consecutive_auto_fails(
    create_managed_node,
    create_observed_node,
    monkeypatch,
):
    """Repeated automatic failures to the same target exclude it from the pool."""
    monkeypatch.setenv("TR_RELIABILITY_CONSECUTIVE_FAILS", "2")
    assert get_reliability_settings().consecutive_fails_cooldown == 2

    source = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=55.0,
        default_location_longitude=-3.5,
        node_id=0xE1000001,
    )
    bad = create_observed_node(
        node_id=0xE10000AA,
        node_id_str=meshtastic_id_to_hex(0xE10000AA),
        last_heard=timezone.now(),
    )
    NodeLatestStatus.objects.create(node=bad, latitude=55.6, longitude=-3.5)
    good = create_observed_node(
        node_id=0xE10000BB,
        node_id_str=meshtastic_id_to_hex(0xE10000BB),
        last_heard=timezone.now(),
    )
    NodeLatestStatus.objects.create(node=good, latitude=55.1, longitude=-3.5)

    now = timezone.now()
    for i in range(2):
        AutoTraceRoute.objects.create(
            source_node=source,
            target_node=bad,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
            status=AutoTraceRoute.STATUS_FAILED,
            triggered_at=now - timedelta(minutes=i),
            completed_at=now - timedelta(minutes=i),
        )

    hard, _soft = load_source_target_reliability(source)
    assert bad.node_id in hard

    picked = pick_traceroute_target(source, slot="test_reliability_hard")
    assert picked is not None
    assert picked.node_id == good.node_id


@pytest.mark.django_db
def test_load_reliability_ignores_non_auto_triggers(
    create_managed_node,
    create_observed_node,
    monkeypatch,
):
    monkeypatch.setenv("TR_RELIABILITY_CONSECUTIVE_FAILS", "2")
    source = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=56.0,
        default_location_longitude=-3.0,
        node_id=0xE2000001,
    )
    target = create_observed_node(
        node_id=0xE20000AA,
        node_id_str=meshtastic_id_to_hex(0xE20000AA),
        last_heard=timezone.now(),
    )
    NodeLatestStatus.objects.create(node=target, latitude=56.8, longitude=-3.0)
    other = create_observed_node(
        node_id=0xE20000BB,
        node_id_str=meshtastic_id_to_hex(0xE20000BB),
        last_heard=timezone.now(),
    )
    NodeLatestStatus.objects.create(node=other, latitude=56.1, longitude=-3.0)

    now = timezone.now()
    for i in range(2):
        AutoTraceRoute.objects.create(
            source_node=source,
            target_node=target,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
            status=AutoTraceRoute.STATUS_FAILED,
            triggered_at=now - timedelta(minutes=i),
            completed_at=now - timedelta(minutes=i),
        )

    hard, _ = load_source_target_reliability(source)
    assert target.node_id not in hard
    assert hard == set()


@pytest.mark.django_db
def test_load_reliability_streak_broken_by_recent_success(
    create_managed_node,
    create_observed_node,
    monkeypatch,
):
    """A completed auto traceroute after failures resets consecutive-fail counting."""
    monkeypatch.setenv("TR_RELIABILITY_CONSECUTIVE_FAILS", "2")
    source = create_managed_node(
        allow_auto_traceroute=True,
        default_location_latitude=57.0,
        default_location_longitude=-3.0,
        node_id=0xE3000001,
    )
    t = create_observed_node(
        node_id=0xE30000AA,
        node_id_str=meshtastic_id_to_hex(0xE30000AA),
        last_heard=timezone.now(),
    )
    NodeLatestStatus.objects.create(node=t, latitude=57.3, longitude=-3.0)

    now = timezone.now()
    AutoTraceRoute.objects.create(
        source_node=source,
        target_node=t,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
        status=AutoTraceRoute.STATUS_FAILED,
        triggered_at=now - timedelta(hours=3),
        completed_at=now - timedelta(hours=3),
    )
    AutoTraceRoute.objects.create(
        source_node=source,
        target_node=t,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
        status=AutoTraceRoute.STATUS_COMPLETED,
        triggered_at=now - timedelta(hours=2),
        completed_at=now - timedelta(hours=2),
    )
    AutoTraceRoute.objects.create(
        source_node=source,
        target_node=t,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
        status=AutoTraceRoute.STATUS_FAILED,
        triggered_at=now - timedelta(hours=1),
        completed_at=now - timedelta(hours=1),
    )

    hard, _ = load_source_target_reliability(source)
    assert t.node_id not in hard
