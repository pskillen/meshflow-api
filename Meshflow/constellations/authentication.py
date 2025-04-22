from django.utils import timezone
from rest_framework import authentication
from rest_framework import exceptions

from .models import NodeAPIKey, NodeAuth


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication class for API keys.

    This class authenticates requests using API keys provided in the Authorization header.
    The header should be in the format: "Authorization: ApiKey <key>"
    """

    def authenticate(self, request):
        # Get the Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        # Check if the header starts with 'ApiKey '
        if not auth_header.startswith('ApiKey '):
            return None

        # Extract the key
        key = auth_header.split(' ')[1].strip()

        try:
            # Find the API key in the database
            api_key = NodeAPIKey.objects.get(key=key, is_active=True)

            # Update the last_used timestamp
            api_key.last_used = timezone.now()
            api_key.save(update_fields=['last_used'])

            # Return the constellation as the authenticated user
            # This allows us to use request.user to access the constellation in views
            return (api_key.constellation, api_key)
        except NodeAPIKey.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid API key')

    def authenticate_header(self, request):
        return 'ApiKey'


class NodeAPIKeyAuthentication(APIKeyAuthentication):
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
        if request.method == 'POST' and request.data:
            # Extract the node ID from the request data
            try:
                from_int = request.data.get('from')

                if from_int is None:
                    raise exceptions.AuthenticationFailed('Missing node ID in request data')

                # Check if the API key is linked to this node
                if not NodeAuth.objects.filter(api_key=api_key, node__node_id=from_int).exists():
                    raise exceptions.AuthenticationFailed('API key not authorized for this node')

            except Exception as e:
                raise exceptions.AuthenticationFailed(f'Error validating node: {str(e)}')

        return auth_result
