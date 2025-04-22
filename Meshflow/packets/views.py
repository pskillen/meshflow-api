from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import PacketIngestSerializer


class PacketIngestView(APIView):
    """
    API endpoint for ingesting packets of any type.

    This endpoint accepts JSON data representing a packet and processes it
    based on the packet type determined by the 'portnum' field.
    """

    def post(self, request, format=None):
        """
        Process a packet ingestion request.

        Args:
            request: The HTTP request object containing the packet data.
            format: The format of the request data (not used).

        Returns:
            Response: A DRF Response object with the result of the ingestion.
        """
        serializer = PacketIngestSerializer(data=request.data)

        if serializer.is_valid():
            try:
                packet = serializer.save()
                return Response(
                    {"status": "success", "message": "Packet ingested successfully"},
                    status=status.HTTP_201_CREATED
                )
            except Exception as e:
                return Response(
                    {"status": "error", "message": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
