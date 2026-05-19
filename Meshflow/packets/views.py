from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.mesh_node_helpers import meshtastic_hex_to_int
from common.protocol import Protocol
from nodes.authentication import NodeAPIKeyAuthentication
from nodes.models import ObservedNode
from nodes.permissions import NodeAuthorizationPermission
from packets.models import (
    AirQualityMetricsPacket,
    DeviceMetricsPacket,
    EnvironmentMetricsPacket,
    HealthMetricsPacket,
    HostMetricsPacket,
    LocalStatsPacket,
    MessagePacket,
    NodeInfoPacket,
    PositionPacket,
    PowerMetricsPacket,
    TraceroutePacket,
    TrafficManagementStatsPacket,
)

from .serializers import NodeSerializer, PacketIngestSerializer
from .signals import (
    air_quality_metrics_packet_received,
    device_metrics_packet_received,
    environment_metrics_packet_received,
    health_metrics_packet_received,
    host_metrics_packet_received,
    local_stats_packet_received,
    message_packet_received,
    node_info_packet_received,
    packet_received,
    position_packet_received,
    power_metrics_packet_received,
    traceroute_packet_received,
    traffic_management_stats_packet_received,
)


class PacketIngestView(APIView):
    """
    Meshtastic packet ingestion endpoint.

    Accepts JSON representing a Meshtastic wire packet (portnum + decoded payload)
    from an authenticated feeder (Node API key). MeshCore ingestion will use
    separate routes when implemented.
    """

    authentication_classes = [NodeAPIKeyAuthentication]
    permission_classes = [NodeAuthorizationPermission]

    def post(self, request, node_id, format=None):
        """Process a packet ingestion request.

        Args:
            request: The HTTP request object containing the packet data.
            node_id: The node ID from the URL.
            format: The format of the request data (not used).

        Returns:
            Response: A DRF Response object with the result of the ingestion.
        """
        # Get the authenticated node from the request
        observer = request.auth.node if hasattr(request.auth, "node") else None
        if not observer:
            return Response(
                {"status": "error", "message": "No authenticated node found"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # if data contains an 'encrypted' field we should skip the packet ingestion
        if request.data.get("encrypted"):
            return Response(
                {"status": "success", "message": "Packet ingested successfully"},
                status=status.HTTP_304_NOT_MODIFIED,
            )

        serializer = PacketIngestSerializer(
            data=request.data,
            context={
                "observer": observer,
                "node_id": node_id,
                "user": request.user,
            },
        )

        if serializer.is_valid():
            try:
                serializer.save()

                packet = serializer.instance
                observation = serializer.observation

                # Send the packet received signal
                packet_received.send(sender=self, packet=packet, observer=observer, observation=observation)

                # Send the specific packet type signals
                if isinstance(packet, MessagePacket):
                    message_packet_received.send(sender=self, packet=packet, observer=observer, observation=observation)
                elif isinstance(packet, PositionPacket):
                    position_packet_received.send(
                        sender=self, packet=packet, observer=observer, observation=observation
                    )
                elif isinstance(packet, DeviceMetricsPacket):
                    device_metrics_packet_received.send(
                        sender=self, packet=packet, observer=observer, observation=observation
                    )
                elif isinstance(packet, LocalStatsPacket):
                    local_stats_packet_received.send(
                        sender=self, packet=packet, observer=observer, observation=observation
                    )
                elif isinstance(packet, NodeInfoPacket):
                    node_info_packet_received.send(
                        sender=self, packet=packet, observer=observer, observation=observation
                    )
                elif isinstance(packet, EnvironmentMetricsPacket):
                    environment_metrics_packet_received.send(
                        sender=self, packet=packet, observer=observer, observation=observation
                    )
                elif isinstance(packet, AirQualityMetricsPacket):
                    air_quality_metrics_packet_received.send(
                        sender=self, packet=packet, observer=observer, observation=observation
                    )
                elif isinstance(packet, HealthMetricsPacket):
                    health_metrics_packet_received.send(
                        sender=self, packet=packet, observer=observer, observation=observation
                    )
                elif isinstance(packet, HostMetricsPacket):
                    host_metrics_packet_received.send(
                        sender=self, packet=packet, observer=observer, observation=observation
                    )
                elif isinstance(packet, PowerMetricsPacket):
                    power_metrics_packet_received.send(
                        sender=self, packet=packet, observer=observer, observation=observation
                    )
                elif isinstance(packet, TrafficManagementStatsPacket):
                    traffic_management_stats_packet_received.send(
                        sender=self, packet=packet, observer=observer, observation=observation
                    )
                elif isinstance(packet, TraceroutePacket):
                    traceroute_packet_received.send(
                        sender=self, packet=packet, observer=observer, observation=observation
                    )

                return Response(
                    {"status": "success", "message": "Packet ingested successfully"},
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                return Response(
                    {"status": "error", "message": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NodeUpsertView(APIView):
    """
    Meshtastic observed-node upsert for feeders (Node API key).

    Creates or updates an ``ObservedNode`` row for Meshtastic ``node_id`` / ``node_id_str``.
    MeshCore will use separate endpoints when implemented.
    """

    authentication_classes = [NodeAPIKeyAuthentication]
    permission_classes = [NodeAuthorizationPermission]

    def post(self, request, node_id, format=None):
        """
        Process a node upsert request.

        Args:
            request: The HTTP request object containing the node data.
            node_id: The node ID from the URL.
            format: The format of the request data (not used).

        Returns:
            Response: A DRF Response object with the result of the upsert operation.
        """
        # Get node_id from request data and sanitize it
        if not node_id:
            return Response(
                {"status": "error", "message": "Node ID is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not request.auth.node.meshtastic_node_id == node_id:
            return Response(
                {"status": "error", "message": "Node ID does not match authenticated node"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Handle different node_id formats
        warnings = []
        if isinstance(node_id, str):
            if node_id.startswith("!"):
                warnings.append("node id should be provided as an integer, not a hex string")
                node_id = meshtastic_hex_to_int(node_id)
            else:
                try:
                    node_id = int(node_id)
                except ValueError:
                    return Response(
                        {"status": "error", "message": "Invalid node ID format"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # Check if node exists
        observed_node_id = request.data.get("id")
        if not observed_node_id:
            return Response(
                {"status": "error", "message": "Node ID is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if isinstance(observed_node_id, str):
            if observed_node_id.startswith("!"):
                warnings.append("node id should be provided as an integer, not a hex string")
                observed_node_id = meshtastic_hex_to_int(observed_node_id)
            else:
                try:
                    observed_node_id = int(observed_node_id)
                except ValueError:
                    return Response(
                        {"status": "error", "message": "Invalid node ID format"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        q = ObservedNode.objects.filter(meshtastic_node_id=observed_node_id, protocol=Protocol.MESHTASTIC)
        if q.exists():
            node = q.first()
            serializer = NodeSerializer(instance=node, data=request.data, partial=True)
        else:
            node = None
            serializer = NodeSerializer(data=request.data, partial=True)

        if serializer.is_valid():
            try:
                serializer.save()

                # Create the response data
                node_data = serializer.data
                node_data.pop("position")
                node_data.pop("device_metrics")

                response_data = {
                    "status": "success",
                    "message": "Node updated successfully" if node else "Node created successfully",
                    "node": node_data,
                }

                # If there are warnings, add them to the response
                if warnings:
                    response_data["warnings"] = warnings

                return Response(
                    response_data,
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                return Response(
                    {"status": "error", "message": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
