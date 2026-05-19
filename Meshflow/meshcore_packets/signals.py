"""MeshCore packet signals (downstream apps subscribe in later phases)."""

from django.dispatch import Signal

meshcore_packet_received = Signal()
meshcore_text_packet_received = Signal()
