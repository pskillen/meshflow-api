"""Tests for traceroute ``source_selection``."""

from datetime import timedelta

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
from nodes.tasks import update_managed_node_statuses
from traceroute.models import AutoTraceRoute
from traceroute.source_selection import (
    SOURCE_SELECTORS,
    eligible_traceroute_sources_ordered,
    select_traceroute_source,
)


@pytest.mark.django_db
def test_select_lru_prefers_never_used_feeder(
    monkeypatch,
    create_managed_node,
    create_packet_observation,
    create_observed_node,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    monkeypatch.setenv("AUTO_TR_SOURCE_SELECTION_ALGO", "least_recently_used")

    a = create_managed_node(allow_auto_traceroute=True, node_id=0xA0000001)
    b = create_managed_node(allow_auto_traceroute=True, node_id=0xA0000002)
    create_packet_observation(observer=a)
    create_packet_observation(observer=b)
    update_managed_node_statuses()
    tgt = create_observed_node(node_id=501)
    AutoTraceRoute.objects.create(
        source_node=a,
        target_node=tgt,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_AUTO,
        status=AutoTraceRoute.STATUS_SENT,
        triggered_at=timezone.now() - timedelta(hours=1),
    )

    picked = select_traceroute_source()
    assert picked.node_id == b.node_id

    ordered = eligible_traceroute_sources_ordered()
    assert [n.node_id for n in ordered] == [b.node_id, a.node_id]


@pytest.mark.django_db
def test_unknown_algo_falls_back_to_default(monkeypatch, create_managed_node, create_packet_observation):
    monkeypatch.setenv("AUTO_TR_SOURCE_SELECTION_ALGO", "not_a_real_algo")
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    mn = create_managed_node(allow_auto_traceroute=True)
    create_packet_observation(observer=mn)
    update_managed_node_statuses()

    assert SOURCE_SELECTORS["least_recently_used"] is not None
    picked = select_traceroute_source()
    assert picked is not None
