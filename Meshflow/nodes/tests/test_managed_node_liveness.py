"""Tests for managed-node traceroute source eligibility (ManagedNodeStatus-backed)."""

import pytest

import nodes.tests.conftest  # noqa: F401
from nodes.managed_node_liveness import (
    eligible_auto_traceroute_sources_queryset,
    is_managed_node_eligible_traceroute_source,
)
from nodes.models import ManagedNodeStatus


@pytest.mark.django_db
def test_eligible_sources_requires_sending_status_and_allow_auto(
    create_managed_node,
    mark_managed_node_feeding,
):
    mn_ok = create_managed_node(allow_auto_traceroute=True, node_id=0xA1000001)
    mark_managed_node_feeding(mn_ok, sending=True)

    mn_disallowed = create_managed_node(allow_auto_traceroute=False, node_id=0xA1000002)
    mark_managed_node_feeding(mn_disallowed, sending=True)

    mn_stale = create_managed_node(allow_auto_traceroute=True, node_id=0xA1000003)
    mark_managed_node_feeding(mn_stale, sending=False)

    mn_no_row = create_managed_node(allow_auto_traceroute=True, node_id=0xA1000004)

    ids = set(eligible_auto_traceroute_sources_queryset().values_list("pk", flat=True))
    assert ids == {mn_ok.pk}
    assert is_managed_node_eligible_traceroute_source(mn_ok) is True
    assert is_managed_node_eligible_traceroute_source(mn_disallowed) is False
    assert is_managed_node_eligible_traceroute_source(mn_stale) is False
    assert is_managed_node_eligible_traceroute_source(mn_no_row) is False


@pytest.mark.django_db
def test_eligible_sources_select_related_status(create_managed_node, mark_managed_node_feeding):
    mn = create_managed_node(allow_auto_traceroute=True)
    mark_managed_node_feeding(mn, sending=True)
    mn_fetched = eligible_auto_traceroute_sources_queryset().get(pk=mn.pk)
    assert mn_fetched.status.is_sending_data is True


@pytest.mark.django_db
def test_refresh_task_aligns_with_eligibility(monkeypatch, create_managed_node, create_packet_observation):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    from nodes.tasks import update_managed_node_statuses

    mn = create_managed_node(allow_auto_traceroute=True)
    create_packet_observation(observer=mn)
    update_managed_node_statuses()
    assert ManagedNodeStatus.objects.get(node=mn).is_sending_data is True
    assert eligible_auto_traceroute_sources_queryset().filter(pk=mn.pk).exists()
