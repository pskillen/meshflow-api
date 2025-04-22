from django.utils import timezone
from rest_framework import authentication
from rest_framework import exceptions

from .models import NodeAPIKey


class NodeAPIKeyAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication class for API keys.

    This class authenticates requests using API keys provided in the Authorization header.
    The header should be in the format: "Authorization: ApiKey <key>"
    """

    def authenticate(self, request):
        # Get the Authorization header
        auth_header = request.META.get('HTTP_X_API_KEY', '')

        if not auth_header:
            return None

        # Extract the key
        key = auth_header

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
        return 'X-API-KEY'
