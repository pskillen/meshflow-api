from rest_framework import exceptions

from nodes.authentication import NodeAPIKeyAuthentication
from nodes.models import NodeAuth


class PacketIngestNodeAPIKeyAuthentication(NodeAPIKeyAuthentication):
    """
    Custom authentication class for API keys that also validates the node.

    This class extends APIKeyAuthentication to also check that the API key
    is linked to the node specified in the request data.
    """

    def authenticate(self, request):
        # First authenticate using the API key
        auth_result = super().authenticate(request)

        if auth_result is None:
            return None

        constellation, api_key = auth_result

        # Check if this is a POST request with data
        if request.method == "POST" and request.data:
            # Extract the node ID from the request data
            try:
                from_int = request.data.get("from")

                if from_int is None:
                    raise exceptions.AuthenticationFailed("Missing node ID in request data")

                # Check if the API key is linked to this node
                if not NodeAuth.objects.filter(api_key=api_key, node__node_id=from_int).exists():
                    raise exceptions.AuthenticationFailed("API key not authorized for this node")

            except Exception as e:
                raise exceptions.AuthenticationFailed(f"Error validating node: {str(e)}")

        return auth_result
