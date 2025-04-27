from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from nodes.models import ObservedNode

from .authentication import NodeAPIKeyAuthentication, PacketIngestNodeAPIKeyAuthentication
from .serializers import NodeSerializer, PacketIngestSerializer


class PacketIngestView(APIView):
    """
    API endpoint for ingesting packets of any type.

    This endpoint accepts JSON data representing a packet and processes it
    based on the packet type determined by the 'portnum' field.

    Authentication is required using an API key that is linked to the node
    specified in the 'from' field of the packet.
    """

    authentication_classes = [PacketIngestNodeAPIKeyAuthentication]

    def post(self, request, format=None):
        """Process a packet ingestion request.

        Args:
            request: The HTTP request object containing the packet data.
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

        serializer = PacketIngestSerializer(data=request.data, context={"observer": observer})

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
    permission_classes = []

    def post(self, request, format=None):
        """
        Process a node upsert request.

        Args:
            request: The HTTP request object containing the node data.
            format: The format of the request data (not used).

        Returns:
            Response: A DRF Response object with the result of the upsert operation.
        """
        # Get node_id from request data
        node_id = request.data.get("id")
        if not node_id:
            return Response(
                {"status": "error", "message": "Node ID is required"},
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
                return Response(
                    {
                        "status": "success",
                        "message": "Node updated successfully" if node else "Node created successfully",
                        "node": serializer.data,
                    },
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                return Response(
                    {"status": "error", "message": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
