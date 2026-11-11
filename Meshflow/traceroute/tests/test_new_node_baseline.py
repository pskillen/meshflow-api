"""Tests for first-seen new-node baseline traceroute enqueue (meshflow-api#236)."""

from unittest.mock import patch

from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext

import pytest

import nodes.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from common.meshtastic_identity import identity_fields, normalise_pubkey
from nodes.models import ObservedNode, ObservedNodeIdentityLink
from packets.models import PacketObservation
from packets.signals import packet_received
from traceroute.dispatch import TRACEROUTE_MAX_PENDING_PER_SOURCE
from traceroute.models import AutoTraceRoute
from traceroute.new_node_baseline import (
    RESULT_DUPLICATE,
    RESULT_NO_ELIGIBLE_SOURCE,
    RESULT_QUEUED,
    RESULT_SOURCE_QUEUE_FULL,
    RESULT_SUCCESSOR,
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
    target = create_observed_node(meshtastic_node_id=0xAAAABEEF)

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
    target = create_observed_node(meshtastic_node_id=0xAAAABEEF)

    assert enqueue_new_node_baseline(target, observer) == RESULT_QUEUED
    assert enqueue_new_node_baseline(target, observer) == RESULT_DUPLICATE


@pytest.mark.django_db
def test_enqueue_no_eligible_source(create_managed_node, create_observed_node):
    observer = create_managed_node(allow_auto_traceroute=False)
    target = create_observed_node(meshtastic_node_id=0xBAD00001)

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
        t = create_observed_node(meshtastic_node_id=0x60000000 + i)
        AutoTraceRoute.objects.create(
            source_node=observer,
            target_node=t,
            trigger_type=AutoTraceRoute.TRIGGER_TYPE_MONITORING,
            trigger_source="test_fill",
            status=AutoTraceRoute.STATUS_PENDING,
        )

    new_target = create_observed_node(meshtastic_node_id=0x70000001)
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
    other = create_managed_node(meshtastic_node_id=222222222, allow_auto_traceroute=True)
    mark_managed_node_feeding(other, sending=True)

    bad_observer = create_managed_node(meshtastic_node_id=333333333, allow_auto_traceroute=False)
    target = create_observed_node(meshtastic_node_id=0xCAFE0001)

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
    assert row.target_node.meshtastic_node_id == 0x12345678


@pytest.mark.django_db
def test_new_node_observed_signal_queues_once(
    create_managed_node,
    create_observed_node,
    mark_managed_node_feeding,
):
    from packets.signals import new_node_observed

    observer = create_managed_node(allow_auto_traceroute=True)
    mark_managed_node_feeding(observer, sending=True)
    target = create_observed_node(meshtastic_node_id=0x51000001)

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
    target = create_observed_node(meshtastic_node_id=0x71000002)

    with patch(
        "traceroute.lifecycle.AutoTraceRoute.objects.create",
        side_effect=IntegrityError("duplicate baseline"),
    ):
        assert enqueue_new_node_baseline(target, observer) == RESULT_DUPLICATE


# --- a node's new number is not a new node -------------------------------------------------------------------------

Link = ObservedNodeIdentityLink
KEY_HEX = normalise_pubkey("I9+3Izg6g7w+TIU+EXGyFVYbh9m9sioXeo6RZdlwnS8=")  # PDYt
OLD, NEW = 0x433B82F0, 0x8959691B


def _link(old, new, state, evidence=Link.Evidence.PUBLIC_KEY):
    return Link.objects.create(
        old_node=old,
        new_node=new,
        evidence=evidence,
        confidence=Link.Confidence.STRONG,
        state=state,
        public_key_hex=KEY_HEX,
    )


@pytest.fixture
def feeding_observer(create_managed_node, mark_managed_node_feeding):
    observer = create_managed_node(allow_auto_traceroute=True)
    mark_managed_node_feeding(observer, sending=True)
    return observer


def _first_packet(create_raw_packet, create_packet_observation, create_user, observer):
    from packets.services.base import BasePacketService

    class _Noop(BasePacketService):
        def _process_packet(self) -> None:
            pass

    pkt = create_raw_packet(from_int=NEW, from_str="!8959691b")
    obs = create_packet_observation(packet=pkt, observer=observer)
    _Noop().process_packet(pkt, observer, obs, create_user())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state, evidence",
    [
        (Link.State.AUTO, Link.Evidence.PUBLIC_KEY),
        (Link.State.CONFIRMED, Link.Evidence.PUBLIC_KEY),
        (Link.State.AUTO, Link.Evidence.PREDICTED_NUMBER),
    ],
)
def test_successor_gets_no_baseline(create_observed_node, feeding_observer, state, evidence):
    old = create_observed_node(meshtastic_node_id=OLD)
    new = create_observed_node(meshtastic_node_id=NEW)
    _link(old, new, state, evidence)

    assert enqueue_new_node_baseline(new, feeding_observer) == RESULT_SUCCESSOR
    assert not AutoTraceRoute.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("state", [Link.State.SUGGESTED, Link.State.REJECTED, None])
def test_non_live_or_no_link_still_queues(create_observed_node, feeding_observer, state):
    old = create_observed_node(meshtastic_node_id=OLD)
    new = create_observed_node(meshtastic_node_id=NEW)
    if state is not None:
        _link(old, new, state)

    assert enqueue_new_node_baseline(new, feeding_observer) == RESULT_QUEUED


@pytest.mark.django_db
def test_first_packet_of_a_predicted_number_queues_no_baseline(
    create_raw_packet, create_packet_observation, create_user, feeding_observer
):
    ObservedNode.objects.create(
        meshtastic_node_id=OLD,
        long_name="old",
        short_name="O",
        meshtastic_public_key=KEY_HEX,
        **identity_fields(KEY_HEX),
    )
    _first_packet(create_raw_packet, create_packet_observation, create_user, feeding_observer)

    assert Link.objects.get().evidence == Link.Evidence.PREDICTED_NUMBER
    assert not AutoTraceRoute.objects.exists()


@pytest.mark.django_db
def test_first_packet_of_an_ordinary_number_still_queues_a_baseline(
    create_raw_packet, create_packet_observation, create_user, feeding_observer
):
    _first_packet(create_raw_packet, create_packet_observation, create_user, feeding_observer)

    assert AutoTraceRoute.objects.filter(
        target_node__meshtastic_node_id=NEW, trigger_type=AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE
    ).exists()


@pytest.mark.django_db
def test_successor_check_is_one_exists_query(create_observed_node):
    from nodes.services.identity_chain import has_live_predecessor

    new = create_observed_node(meshtastic_node_id=NEW)
    with CaptureQueriesContext(connection) as ctx:
        assert has_live_predecessor(new) is False
    assert len(ctx) == 1
    assert "LIMIT 1" in ctx.captured_queries[0]["sql"].upper()
