from rest_framework import permissions

from nodes.models import NodeAuth


def _reject(request, view):
    """Count a legacy-URL rejection (code ``not_linked``) and refuse."""
    from common.feeder_metrics import record_feeder_auth_rejection

    get_api = getattr(view, "get_feeder_api", None)
    try:
        api = get_api(request) if get_api else "unknown"
    except Exception:
        api = "unknown"
    record_feeder_auth_rejection(api=api, code="not_linked")
    return False


class NodeAuthorizationPermission(permissions.BasePermission):
    """
    Permission class that checks if the authenticated node is authorized to act on behalf of the requested node_id.
    Also attaches the authorized node to the request auth context.
    """

    def has_permission(self, request, view):
        # Get the node_id from the URL parameters
        node_id = view.kwargs.get("node_id")
        if not node_id:
            return _reject(request, view)

        # Ensure the request has an authenticated user
        if not hasattr(request, "auth") and not request.auth:
            return _reject(request, view)

        # Get the NodeAuth instance
        try:
            node_auth = NodeAuth.objects.select_related("node").get(
                api_key=request.auth, node__meshtastic_node_id=node_id
            )
            if node_auth.node.deleted_at is not None:
                return _reject(request, view)
            # Attach the node to the request auth context
            request.auth.node = node_auth.node
            return True
        except NodeAuth.DoesNotExist:
            return _reject(request, view)
