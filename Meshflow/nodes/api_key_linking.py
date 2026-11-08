"""Rule: an API key may be linked to only one active feeder (ADR-0005).

Existing shared links keep working on the legacy URLs; this module only gates *new* links.
A feeder may still hold two keys during a rotation, so the limit is per key, not per feeder.
"""

from rest_framework import status
from rest_framework.exceptions import APIException

API_KEY_ALREADY_LINKED_CODE = "api_key_already_linked"
API_KEY_ALREADY_LINKED_MESSAGE = "This API key is already linked to a feeder. Create a separate key for each feeder."


class ApiKeyAlreadyLinked(APIException):
    """400 with body ``{"error": ..., "code": "api_key_already_linked"}``."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = {"error": API_KEY_ALREADY_LINKED_MESSAGE, "code": API_KEY_ALREADY_LINKED_CODE}
    default_code = API_KEY_ALREADY_LINKED_CODE


def api_key_can_link(api_key, node) -> bool:
    """False when ``api_key`` already has an active link to a node other than ``node``."""
    return not api_key.node_links.filter(node__deleted_at__isnull=True).exclude(node=node).exists()
