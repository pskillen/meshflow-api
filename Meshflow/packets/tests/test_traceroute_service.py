"""Tests for TraceroutePacketService signal emission."""

from unittest.mock import patch

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from packets.services.traceroute import TraceroutePacketService
from packets.signals import auto_traceroute_completed_from_packet
from traceroute.models import AutoTraceRoute


@pytest.mark.django_db
def test_traceroute_service_emits_completion_signal(
    create_managed_node,
    create_observed_node,
    create_traceroute_packet,
    create_packet_observation,
    create_user,
):
    source = create_managed_node()
    target = create_observed_node(meshtastic_node_id=0xABCD1234)
    user = create_user()
    packet = create_traceroute_packet(
        observer=source,
        from_int=target.meshtastic_node_id,
        route=[],
        route_back=[],
    )
    observation = create_packet_observation(packet=packet, observer=source)
    now = timezone.now()
    packet.first_reported_time = now
    packet.save(update_fields=["first_reported_time"])
    auto_tr = AutoTraceRoute.objects.create(
        source_node=source,
        target_node=target,
        status=AutoTraceRoute.STATUS_SENT,
        triggered_at=now,
    )

    with patch.object(auto_traceroute_completed_from_packet, "send") as mock_send:
        TraceroutePacketService().process_packet(packet, source, observation, user)

    mock_send.assert_called_once()
    _, kwargs = mock_send.call_args
    assert kwargs["auto_tr"].status == AutoTraceRoute.STATUS_COMPLETED
    assert kwargs["traceroute_packet"] == packet
    assert kwargs["packet_observation"] == observation
    assert kwargs["observer"] == source
    assert kwargs["from_node"] == target
