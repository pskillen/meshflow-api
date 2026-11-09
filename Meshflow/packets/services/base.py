"""Base service for packet processing."""

import abc

from django.utils import timezone

from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import ManagedNode, ObservedNode
from nodes.services.observed_nodes import get_or_create_meshtastic_observed_node
from packets.hops import update_inferred_max_hops
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
            display_id = self.packet.from_str if self.packet.from_str else meshtastic_id_to_hex(self.packet.from_int)
            self.from_node, created = get_or_create_meshtastic_observed_node(
                self.packet.from_int,
                defaults={
                    "long_name": "Unknown Node " + display_id,
                    "short_name": display_id[-4:] if len(display_id) >= 4 else "????",
                },
            )
            if created:
                self._dx_previous_last_heard = None
                self._dx_from_node_created = True
                new_node_observed.send(sender=self, node=self.from_node, observer=self.observer)
            else:
                self._dx_previous_last_heard = self.from_node.last_heard
        else:
            raise ValueError("Packet has no from_int")

    def _update_inferred_max_hops(self, port_num: str) -> None:
        """Update the sender's inferred max hops from this packet's observation (see packets.hops)."""
        update_inferred_max_hops(self.from_node, self.observation, port_num)

    def _update_node_last_heard(self) -> None:
        """Move the sender's last_heard forward only (never back, never past now)."""
        if self.packet.from_int and self.packet.first_reported_time:
            try:
                # first_reported_time can be old (late upload) or in the future (feeder clock): cap it at now.
                candidate = min(self.packet.first_reported_time, timezone.now())
                current = self.from_node.last_heard
                if current is not None and candidate <= current:
                    return
                self.from_node.last_heard = candidate
                self.from_node.save(update_fields=["last_heard"])
                node_last_heard_advanced.send(
                    sender=self.__class__,
                    observed_node=self.from_node,
                    last_heard=candidate,
                )
            except ObservedNode.DoesNotExist:
                # If the node doesn't exist, we don't need to update it
                pass
