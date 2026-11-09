"""last_heard only moves forward and never past now (#455)."""

from datetime import timedelta

from django.utils import timezone

import pytest

from nodes.models import ObservedNode
from packets.services.device_metrics import DeviceMetricsPacketService
from packets.signals import node_last_heard_advanced


def _run(create_device_metrics_packet, create_managed_node, create_packet_observation, create_user, *, first, before):
    packet = create_device_metrics_packet()
    packet.first_reported_time = first
    packet.save()
    observer = create_managed_node()
    observation = create_packet_observation(packet=packet, observer=observer)
    node = ObservedNode.objects.get_or_create(meshtastic_node_id=packet.from_int)[0]
    node.last_heard = before
    node.save()

    seen = []

    def handler(sender, **kwargs):
        seen.append(kwargs["last_heard"])

    node_last_heard_advanced.connect(handler)
    try:
        DeviceMetricsPacketService().process_packet(packet, observer, observation, create_user())
    finally:
        node_last_heard_advanced.disconnect(handler)
    node.refresh_from_db()
    return node, seen


@pytest.mark.django_db
def test_older_packet_does_not_move_last_heard_back(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    now = timezone.now()
    before = now - timedelta(hours=1)
    node, seen = _run(
        create_device_metrics_packet,
        create_managed_node,
        create_packet_observation,
        create_user,
        first=now - timedelta(hours=5),
        before=before,
    )
    assert node.last_heard == before
    assert seen == []


@pytest.mark.django_db
def test_newer_packet_advances_last_heard_and_signals(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    now = timezone.now()
    first = now - timedelta(minutes=5)
    node, seen = _run(
        create_device_metrics_packet,
        create_managed_node,
        create_packet_observation,
        create_user,
        first=first,
        before=now - timedelta(hours=1),
    )
    assert node.last_heard == first
    assert seen == [first]


@pytest.mark.django_db
def test_future_packet_time_is_capped_at_now(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    start = timezone.now()
    node, seen = _run(
        create_device_metrics_packet,
        create_managed_node,
        create_packet_observation,
        create_user,
        first=start + timedelta(days=3),
        before=start - timedelta(hours=1),
    )
    assert start <= node.last_heard <= timezone.now()
    assert seen == [node.last_heard]


@pytest.mark.django_db
def test_first_packet_sets_last_heard_when_none(
    create_device_metrics_packet, create_managed_node, create_packet_observation, create_user
):
    first = timezone.now() - timedelta(minutes=2)
    node, seen = _run(
        create_device_metrics_packet,
        create_managed_node,
        create_packet_observation,
        create_user,
        first=first,
        before=None,
    )
    assert node.last_heard == first
    assert seen == [first]
