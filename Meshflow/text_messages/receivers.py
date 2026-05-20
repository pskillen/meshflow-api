"""Text message signal receivers."""

from django.dispatch import receiver

from meshcore_packets.signals import meshcore_text_packet_received
from meshcore_packets.services.text_message import handle_meshcore_text_packet


@receiver(meshcore_text_packet_received)
def on_meshcore_text_packet_received(sender, packet, observer, observation, **kwargs):
    handle_meshcore_text_packet(sender, packet=packet, observer=observer, observation=observation, **kwargs)
