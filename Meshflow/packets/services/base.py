"""Base service for packet processing."""

import abc

from nodes.models import ManagedNode, ObservedNode
from packets.models import PacketObservation, RawPacket
from packets.signals import new_node_observed
from users.models import User


class BasePacketService(abc.ABC):
    """Base service for processing packets."""

    packet: RawPacket
    observer: ManagedNode
    observation: PacketObservation
    from_node: ObservedNode
    user: User

    def __init__(self):
        """Initialize the service with a packet and its observer."""

    def process_packet(
        self, packet: RawPacket, observer: ManagedNode, observation: PacketObservation, user: User
    ) -> None:
        """Process the packet and create any necessary related records."""
        self.packet = packet
        self.observer = observer
        self.observation = observation
        self.user = user

        self._get_or_create_from_node()
        self._process_packet()
        self._update_node_last_heard()

    @abc.abstractmethod
    def _process_packet(self) -> None:
        """Process the packet and create any necessary related records."""
        pass

    def _get_or_create_from_node(self) -> ObservedNode:
        """Get or create the from node."""
        if self.packet.from_int:
            try:
                self.from_node = ObservedNode.objects.get(node_id=self.packet.from_int)
            except ObservedNode.DoesNotExist:
                self.from_node = ObservedNode.objects.create(node_id=self.packet.from_int)
                new_node_observed.send(sender=self, node=self.from_node, observer=self.observer)
        else:
            raise ValueError("Packet has no from_int")

    def _update_node_last_heard(self) -> None:
        """Update the last_heard timestamp of the node that sent the packet."""
        if self.packet.from_int and self.packet.first_reported_time:
            try:
                self.from_node.last_heard = self.packet.first_reported_time
                self.from_node.save(update_fields=["last_heard"])
            except ObservedNode.DoesNotExist:
                # If the node doesn't exist, we don't need to update it
                pass
