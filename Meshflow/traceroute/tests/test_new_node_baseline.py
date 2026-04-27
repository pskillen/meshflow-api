"""Tests for first-seen new-node baseline traceroute enqueue (meshflow-api#236)."""

from unittest.mock import patch

from django.db import IntegrityError

import pytest

import nodes.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from packets.models import PacketObservation
from packets.signals import packet_received
from traceroute.dispatch import TRACEROUTE_MAX_PENDING_PER_SOURCE
from traceroute.models import AutoTraceRoute
from traceroute.new_node_baseline import (
    RESULT_DUPLICATE,
    RESULT_NO_ELIGIBLE_SOURCE,
    RESULT_QUEUED,
    RESULT_SOURCE_QUEUE_FULL,
    enqueue_new_node_baseline,
)


@pytest.mark.django_db
def test_enqueue_creates_pending_new_node_baseline(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
):
    observer = create_managed_node(allow_auto_traceroute=True)
    mark_managed_node_feeding(observer, sending=True)
    target = create_observed_node(node_id=0xAAAABEEF)

    r = enqueue_new_node_baseline(target, observer)
    assert r == RESULT_QUEUED

    row = AutoTraceRoute.objects.get(
        target_node=target,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE,
    )
    assert row.status == AutoTraceRoute.STATUS_PENDING
    assert row.source_node_id == observer.pk
    assert row.trigger_source == "new_node_observed"


@pytest.mark.django_db
def test_enqueue_duplicate_second_call(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
):
    observer = create_managed_node(allow_auto_traceroute=True)
    mark_managed_node_feeding(observer, sending=True)
    target = create_observed_node(node_id=0xAAAABEEF)

    assert enqueue_new_node_baseline(target, observer) == RESULT_QUEUED
    assert enqueue_new_node_baseline(target, observer) == RESULT_DUPLICATE


@pytest.mark.django_db
def test_enqueue_no_eligible_source(create_managed_node, create_observed_node):
    observer = create_managed_node(allow_auto_traceroute=False)
    target = create_observed_node(node_id=0xBAD00001)

    assert enqueue_new_node_baseline(target, observer) == RESULT_NO_ELIGIBLE_SOURCE
    assert not AutoTraceRoute.objects.filter(target_node=target).exists()


@pytest.mark.django_db
def test_enqueue_source_queue_full(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
):
    observer = create_managed_node(allow_auto_traceroute=True)
    mark_managed_node_feeding(observer, sending=True)
    for i in range(TRACEROUTE_MAX_PENDING_PER_SOURCE):
        t = create_observed_node(node_id=0x60000000 + i)
        AutoTraceRoute.objects.create(
            source_node=observer,
            target_node=t,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
            trigger_source="test_fill",
            status=AutoTraceRoute.STATUS_PENDING,
        )

    new_target = create_observed_node(node_id=0x70000001)
    assert enqueue_new_node_baseline(new_target, observer) == RESULT_SOURCE_QUEUE_FULL


@pytest.mark.django_db
def test_enqueue_prefers_other_source_when_observer_ineligible_but_cluster_has_feeder(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
):
    """
    Observer may not be auto-traceroute-eligible; another eligible feeder can still run the TR.
    """
    other = create_managed_node(node_id=222222222, allow_auto_traceroute=True)
    mark_managed_node_feeding(other, sending=True)

    bad_observer = create_managed_node(node_id=333333333, allow_auto_traceroute=False)
    target = create_observed_node(node_id=0xCAFE0001)

    r = enqueue_new_node_baseline(target, bad_observer)
    assert r == RESULT_QUEUED
    row = AutoTraceRoute.objects.get(target_node=target)
    assert row.source_node_id == other.pk


@pytest.mark.django_db
def test_packet_received_inferred_path_queues_baseline(
    create_managed_node,
    create_message_packet,
    mark_managed_node_feeding,
):
    observer = create_managed_node(allow_auto_traceroute=True)
    mark_managed_node_feeding(observer, sending=True)

    packet = create_message_packet(from_int=0x12345678, from_str="!12345678")
    from constellations.models import MessageChannel

    channel = MessageChannel.objects.create(
        name="Test Channel",
        constellation=observer.constellation,
    )
    observation = PacketObservation.objects.create(
        packet=packet,
        observer=observer,
        channel=channel,
        hop_limit=5,
        hop_start=5,
        rx_time=packet.first_reported_time,
    )

    assert not AutoTraceRoute.objects.exists()

    packet_received.send(sender=None, packet=packet, observer=observer, observation=observation)

    row = AutoTraceRoute.objects.get(trigger_type=AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE)
    assert row.source_node_id == observer.pk
    assert row.target_node.node_id == 0x12345678


@pytest.mark.django_db
def test_new_node_observed_signal_queues_once(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
):
    from packets.signals import new_node_observed

    observer = create_managed_node(allow_auto_traceroute=True)
    mark_managed_node_feeding(observer, sending=True)
    target = create_observed_node(node_id=0x51000001)

    new_node_observed.send(sender=None, node=target, observer=observer)

    assert AutoTraceRoute.objects.filter(trigger_type=AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE).count() == 1


@pytest.mark.django_db
def test_enqueue_integrity_error_returns_duplicate(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
):
    observer = create_managed_node(allow_auto_traceroute=True)
    mark_managed_node_feeding(observer, sending=True)
    target = create_observed_node(node_id=0x71000002)

    with patch(
        "traceroute.new_node_baseline.AutoTraceRoute.objects.create",
        side_effect=IntegrityError("duplicate baseline"),
    ):
        assert enqueue_new_node_baseline(target, observer) == RESULT_DUPLICATE
