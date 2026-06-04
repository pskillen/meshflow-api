"""TextMessage WebSocket payload serialization."""

from django.utils import timezone

import pytest

from common.protocol import Protocol
from constellations.models import MessageChannel
from text_messages.models import TextMessage
from ws.serializers import TextMessageWSSerializer


@pytest.mark.django_db
def test_ws_serializer_includes_meshtastic_protocol(create_constellation, create_observed_node):
    constellation = create_constellation()
    channel = MessageChannel.objects.create(name="LongFast", constellation=constellation)
    sender = create_observed_node()
    message = TextMessage.objects.create(
        protocol=Protocol.MESHTASTIC,
        sender=sender,
        channel=channel,
        sent_at=timezone.now(),
        message_text="hello mt",
    )

    data = TextMessageWSSerializer(message).data

    assert data["protocol"] == "meshtastic"
    assert data["channel"] == channel.id


@pytest.mark.django_db
def test_ws_serializer_includes_meshcore_protocol(create_constellation):
    constellation = create_constellation()
    channel = MessageChannel.objects.create(
        name="Public",
        constellation=constellation,
        protocol=Protocol.MESHCORE,
    )
    message = TextMessage.objects.create(
        protocol=Protocol.MESHCORE,
        sender=None,
        channel=channel,
        sent_at=timezone.now(),
        message_text="hello mc",
    )

    data = TextMessageWSSerializer(message).data

    assert data["protocol"] == "meshcore"
    assert data["channel"] == channel.id
    assert data["original_mc_packet_id"] is None
