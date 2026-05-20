"""Base service for packet processing."""

import abc

from common.mesh_node_helpers import meshtastic_id_to_hex
from common.protocol import Protocol
from nodes.models import ManagedNode, ObservedNode
from packets.models import MtRawPacket, PacketObservation
from packets.signals import new_node_observed, node_last_heard_advanced, packet_from_node_processed
from users.models import User


class BasePacketService(abc.ABC):
    """Base service for processing packets."""

    packet: MtRawPacket
    observer: ManagedNode
    observation: PacketObservation
    from_node: ObservedNode
    user: User

    def __init__(self):
        """Initialize the service with a packet and its observer."""

    def process_packet(
        self, packet: MtRawPacket, observer: ManagedNode, observation: PacketObservation, user: User
    ) -> None:
        """Process the packet and create any necessary related records."""
        self.packet = packet
        self.observer = observer
        self.observation = observation
        self.user = user

        self._dx_from_node_created = False
        self._dx_previous_last_heard = None
        self._get_or_create_from_node()
        self._process_packet()
        packet_from_node_processed.send(
            sender=self.__class__,
            packet=self.packet,
            observer=self.observer,
            observation=self.observation,
            from_node=self.from_node,
            previous_last_heard=self._dx_previous_last_heard,
            from_node_created=self._dx_from_node_created,
        )
        self._update_node_last_heard()

    @abc.abstractmethod
    def _process_packet(self) -> None:
        """Process the packet and create any necessary related records."""
        pass

    def _get_or_create_from_node(self) -> ObservedNode:
        """Get or create the from node."""
        if self.packet.from_int:
            try:
                self.from_node = ObservedNode.objects.get(
                    meshtastic_node_id=self.packet.from_int,
                    protocol=Protocol.MESHTASTIC,
                )
                self._dx_previous_last_heard = self.from_node.last_heard
            except ObservedNode.DoesNotExist:
                self._dx_previous_last_heard = None
                display_id = (
                    self.packet.from_str if self.packet.from_str else meshtastic_id_to_hex(self.packet.from_int)
                )
                self.from_node = ObservedNode.objects.create(
                    protocol=Protocol.MESHTASTIC,
                    meshtastic_node_id=self.packet.from_int,
                    long_name="Unknown Node " + display_id,
                    short_name=display_id[-4:] if len(display_id) >= 4 else "????",
                )
                self._dx_from_node_created = True
                new_node_observed.send(sender=self, node=self.from_node, observer=self.observer)
        else:
            raise ValueError("Packet has no from_int")

    def _update_node_last_heard(self) -> None:
        """Update the last_heard timestamp of the node that sent the packet."""
        if self.packet.from_int and self.packet.first_reported_time:
            try:
                last_heard = self.packet.first_reported_time
                self.from_node.last_heard = last_heard
                self.from_node.save(update_fields=["last_heard"])
                node_last_heard_advanced.send(
                    sender=self.__class__,
                    observed_node=self.from_node,
                    last_heard=last_heard,
                )
            except ObservedNode.DoesNotExist:
                # If the node doesn't exist, we don't need to update it
                pass
