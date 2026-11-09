"""Service for packets with no typed processing (generic ports, LocalStats, traffic management stats)."""

from packets.services.base import BasePacketService


class GenericPacketService(BasePacketService):
    """No-op service: the base class resolves the sender and advances ``last_heard``."""

    def _process_packet(self) -> None:
        """Nothing to derive from the payload."""
