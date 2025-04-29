from django.utils import timezone

from rest_framework import authentication, exceptions

from .models import NodeAPIKey


class NodeAPIKeyAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication class for API keys.

    This class authenticates requests using API keys provided in either:
    1. X-API-KEY header
    2. Authorization: Token <key> header
    """

    def authenticate(self, request):
        # Try to get the API key from X-API-KEY header first
        auth_header = request.META.get("HTTP_X_API_KEY", "")

        # If not found, try the Authorization header
        if not auth_header or auth_header.strip() == "":
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            if auth_header.startswith("Token "):
                auth_header = auth_header.split(" ")[1]
            else:
                raise exceptions.AuthenticationFailed(
                    "Invalid authorization header: use Token <key> (or preferably x-api-key)"
                )

        if not auth_header or auth_header.strip() == "":
            raise exceptions.AuthenticationFailed("API key is required (x-api-key or authorization header)")

        # Extract the key
        key = auth_header

        try:
            # Find the API key in the database
            api_key = NodeAPIKey.objects.get(key=key, is_active=True)

            # Update the last_used timestamp
            api_key.last_used = timezone.now()
            api_key.save(update_fields=["last_used"])

            # Return the user as the authenticated user
            # This allows us to use request.user to access the user in views
            return (api_key.owner, api_key)
        except NodeAPIKey.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid API key")

    def authenticate_header(self, request):
        return "X-API-KEY"
