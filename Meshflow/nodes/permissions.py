from rest_framework import permissions

from nodes.models import NodeAuth


class NodeAuthorizationPermission(permissions.BasePermission):
    """
    Permission class that checks if the authenticated node is authorized to act on behalf of the requested node_id.
    Also attaches the authorized node to the request auth context.
    """

    def has_permission(self, request, view):
        # Get the node_id from the URL parameters
        node_id = view.kwargs.get("node_id")
        if not node_id:
            return False

        # Ensure the request has an authenticated user
        if not hasattr(request, "auth") and not request.auth:
            return False

        # Get the NodeAuth instance
        try:
            node_auth = NodeAuth.objects.get(api_key=request.auth, node__node_id=node_id)
            # Attach the node to the request auth context
            request.auth.node = node_auth.node
            return True
        except NodeAuth.DoesNotExist:
            return False
