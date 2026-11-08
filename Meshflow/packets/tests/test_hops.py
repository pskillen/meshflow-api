"""Tests for packets.hops: inferred max hops rules and unknown-hop helpers."""

from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone

import pytest

from nodes.models import NodeLatestStatus
from nodes.tests.conftest import create_observed_node, observed_node_data  # noqa: F401
from packets.hops import (
    observation_hop_count,
    observation_is_direct,
    update_inferred_max_hops,
)


def obs(hop_start, hop_limit=None, bitfield=None):
    limit = hop_start if hop_limit is None else hop_limit
    return SimpleNamespace(hop_start=hop_start, hop_limit=limit, bitfield=bitfield)


@pytest.fixture
def node(create_observed_node):  # noqa: F811
    return create_observed_node()


def status_of(node):
    return NodeLatestStatus.objects.get(node=node)


def age_value(node, days):
    NodeLatestStatus.objects.filter(node=node).update(
        meshtastic_inferred_max_hops_at=timezone.now() - timedelta(days=days)
    )


@pytest.mark.django_db
def test_text_then_position_keeps_text_value(node):
    assert update_inferred_max_hops(node, obs(3), "TEXT_MESSAGE_APP") is True
    assert update_inferred_max_hops(node, obs(1), "POSITION_APP") is False
    assert status_of(node).meshtastic_inferred_max_hops == 3


@pytest.mark.django_db
def test_authoritative_can_lower(node):
    update_inferred_max_hops(node, obs(4), "TEXT_MESSAGE_APP")
    update_inferred_max_hops(node, obs(2), "TEXT_MESSAGE_APP")
    assert status_of(node).meshtastic_inferred_max_hops == 2


@pytest.mark.django_db
@pytest.mark.parametrize("port", ["TRACEROUTE_APP", "ROUTING_APP", "ADMIN_APP", "STORE_FORWARD_APP", "PORT_999"])
def test_unscaled_ports_are_authoritative(node, port):
    update_inferred_max_hops(node, obs(5), "TEXT_MESSAGE_APP")
    update_inferred_max_hops(node, obs(2), port)
    status = status_of(node)
    assert status.meshtastic_inferred_max_hops == 2
    assert status.meshtastic_inferred_max_hops_source == port


@pytest.mark.django_db
@pytest.mark.parametrize("port", ["POSITION_APP", "TELEMETRY_APP", "NODEINFO_APP", "NEIGHBORINFO_APP"])
def test_scaled_ports_only_raise_when_authoritative_is_old(node, port):
    update_inferred_max_hops(node, obs(3), "TEXT_MESSAGE_APP")
    # Fresh authoritative value: scaled 5 does not raise it
    assert update_inferred_max_hops(node, obs(5), port) is False
    assert status_of(node).meshtastic_inferred_max_hops == 3

    age_value(node, 8)
    # Old authoritative value: scaled 5 raises it
    assert update_inferred_max_hops(node, obs(5), port) is True
    status = status_of(node)
    assert status.meshtastic_inferred_max_hops == 5
    assert status.meshtastic_inferred_max_hops_source == port


@pytest.mark.django_db
def test_scaled_never_lowers_even_when_authoritative_is_old(node):
    update_inferred_max_hops(node, obs(5), "TEXT_MESSAGE_APP")
    age_value(node, 30)
    assert update_inferred_max_hops(node, obs(1), "POSITION_APP") is False
    assert status_of(node).meshtastic_inferred_max_hops == 5


@pytest.mark.django_db
def test_scaled_raises_legacy_row_without_at_or_source(node):
    NodeLatestStatus.objects.create(node=node, meshtastic_inferred_max_hops=2)
    assert update_inferred_max_hops(node, obs(4), "POSITION_APP") is True
    assert status_of(node).meshtastic_inferred_max_hops == 4


@pytest.mark.django_db
def test_scaled_sets_first_value(node):
    assert update_inferred_max_hops(node, obs(3), "TELEMETRY_APP") is True
    status = status_of(node)
    assert status.meshtastic_inferred_max_hops == 3
    assert status.meshtastic_inferred_max_hops_source == "TELEMETRY_APP"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "observation,kwargs",
    [
        (obs(None, None), {}),
        (obs(2, 3), {}),  # hop_start < hop_limit
        (obs(0, 0), {}),  # hop_start 0, no bitfield
        (obs(3), {"via_mqtt": True}),
    ],
)
def test_ignore_cases_leave_value_alone(node, observation, kwargs):
    update_inferred_max_hops(node, obs(4), "TEXT_MESSAGE_APP")
    before = status_of(node)
    assert update_inferred_max_hops(node, observation, "TEXT_MESSAGE_APP", **kwargs) is False
    after = status_of(node)
    assert after.meshtastic_inferred_max_hops == 4
    assert after.meshtastic_inferred_max_hops_at == before.meshtastic_inferred_max_hops_at


@pytest.mark.django_db
def test_ignored_observation_does_not_create_status(node):
    assert update_inferred_max_hops(node, obs(0, 0), "TEXT_MESSAGE_APP") is False
    assert not NodeLatestStatus.objects.filter(node=node).exists()


@pytest.mark.django_db
def test_hop_start_zero_with_bitfield_is_stored(node):
    assert update_inferred_max_hops(node, obs(0, 0, bitfield=0), "TEXT_MESSAGE_APP") is True
    assert status_of(node).meshtastic_inferred_max_hops == 0


@pytest.mark.django_db
def test_at_and_source_written(node):
    before = timezone.now()
    update_inferred_max_hops(node, obs(3), "TRACEROUTE_APP")
    status = status_of(node)
    assert status.meshtastic_inferred_max_hops_source == "TRACEROUTE_APP"
    assert before <= status.meshtastic_inferred_max_hops_at <= timezone.now()


@pytest.mark.parametrize(
    "start,limit,bitfield,count,direct",
    [
        (3, 3, None, 0, True),
        (3, 1, None, 2, False),
        (0, 0, None, None, False),  # unknown
        (0, 0, 0, 0, True),
        (0, 0, 1, 0, True),
        (3, 0, None, 3, False),  # hops exhausted
        (2, 3, None, None, False),  # inconsistent: never negative
        (None, 3, None, None, False),
        (3, None, None, None, False),
    ],
)
def test_hop_count_and_direct(start, limit, bitfield, count, direct):
    observation = SimpleNamespace(hop_start=start, hop_limit=limit, bitfield=bitfield)
    assert observation_hop_count(observation) == count
    assert observation_is_direct(observation) is direct
