from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.mesh_node_helpers import meshtastic_hex_to_int
from nodes.authentication import NodeAPIKeyAuthentication
from nodes.models import ObservedNode
from nodes.permissions import NodeAuthorizationPermission

from .serializers import NodeSerializer, PacketIngestSerializer


class PacketIngestView(APIView):
    """
    API endpoint for ingesting packets of any type.

    This endpoint accepts JSON data representing a packet and processes it
    based on the packet type determined by the 'portnum' field.

    Authentication is required using an API key that is linked to the node
    specified in the 'from' field of the packet.
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

        serializer = PacketIngestSerializer(data=request.data, context={"observer": observer, "node_id": node_id})

        if serializer.is_valid():
            try:
                serializer.save()
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
    API endpoint for upserting node information.

    This endpoint allows a node to update its own information using its API key.
    If the node doesn't exist, it will be created. This is an upsert operation.

    Authentication is required using the node's API key.
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
        if not request.auth.node.node_id == node_id:
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
        try:
            node = ObservedNode.objects.get(node_id=node_id)
            serializer = NodeSerializer(instance=node, data=request.data, partial=True)
        except ObservedNode.DoesNotExist:
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
