"""Normalize MeshCore text packets into TextMessage rows."""

import logging

from common.meshcore_node_helpers import resolve_or_create_mc_observed_node
from common.protocol import Protocol
from meshcore_packets.models import MeshCorePayloadType, MeshCoreTextPacket
from packets.signals import text_message_received
from text_messages.models import TextMessage

logger = logging.getLogger(__name__)


class MeshCoreTextMessageService:
    """Create TextMessage from ingested MeshCoreTextPacket."""

    def process_packet(self, packet: MeshCoreTextPacket, observer, observation) -> TextMessage | None:
        if TextMessage.objects.filter(original_mc_packet=packet).exists():
            return None

        if packet.payload_type == MeshCorePayloadType.CHANNEL_TEXT:
            return self._create_channel_message(packet, observation)
        if packet.payload_type == MeshCorePayloadType.CONTACT_TEXT:
            return self._create_contact_message(packet)
        return None

    def _create_channel_message(self, packet: MeshCoreTextPacket, observation) -> TextMessage | None:
        message = TextMessage.objects.create(
            protocol=Protocol.MESHCORE,
            original_mc_packet=packet,
            sender=None,
            recipient_meshtastic_node_id=None,
            channel=packet.channel or observation.channel,
            sent_at=packet.rx_time,
            message_text=packet.text,
            is_emoji=False,
        )
        text_message_received.send(sender=self, message=message, observer=observation.observer)
        return message

    def _create_contact_message(self, packet: MeshCoreTextPacket) -> TextMessage | None:
        prefix = packet.from_pubkey_prefix
        if not prefix and packet.from_pubkey:
            prefix = packet.from_pubkey[:12]

        sender = None
        if prefix:
            sender = resolve_or_create_mc_observed_node(
                mc_pubkey=packet.from_pubkey,
                mc_pubkey_prefix=prefix if not packet.from_pubkey else None,
                last_heard=packet.rx_time,
            )

        return TextMessage.objects.create(
            protocol=Protocol.MESHCORE,
            original_mc_packet=packet,
            sender=sender,
            recipient_meshtastic_node_id=None,
            channel=None,
            sent_at=packet.rx_time,
            message_text=packet.text,
            is_emoji=False,
        )


def handle_meshcore_text_packet(sender, packet, observer, observation, **kwargs):
    """Signal receiver: meshcore_text_packet_received → TextMessage."""
    if not isinstance(packet, MeshCoreTextPacket):
        return
    MeshCoreTextMessageService().process_packet(packet, observer, observation)
