from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from constellations.models import ConstellationUserMembership
from nodes.models import NodeAPIKey, NodeAuth, ObservedNode, ManagedNode
from nodes.serializers import (
    APIKeyCreateSerializer,
    APIKeyDetailSerializer,
    APIKeySerializer,
)


class APIKeyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for API keys.

    Allows users to create, view, update, and delete API keys for constellations
    they have admin or editor access to.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filter API keys to only show those for constellations the user has access to.
        """
        user = self.request.user
        return NodeAPIKey.objects.filter(
            constellation__memberships__user=user,
            constellation__memberships__role__in=["admin", "editor"],
        ).distinct()

    def get_serializer_class(self):
        """
        Return different serializers based on the action.
        """
        if self.action == "create":
            return APIKeyCreateSerializer
        elif self.action in ["retrieve", "list"]:
            return APIKeyDetailSerializer
        return APIKeySerializer

    def perform_create(self, serializer):
        """
        Create a new API key and ensure the user has proper permissions.
        """
        constellation = serializer.validated_data["constellation"]

        # Check if user has permission to create API keys for this constellation
        if not ConstellationUserMembership.objects.filter(
            user=self.request.user,
            constellation=constellation,
            role__in=["admin", "editor"],
        ).exists():
            raise permissions.PermissionDenied(
                "You don't have permission to create API keys for this constellation."
            )

        serializer.save(owner=self.request.user, created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def add_node(self, request, pk=None):
        """
        Add a node to an API key.
        """
        api_key = self.get_object()
        node_id = request.data.get("node_id")

        if not node_id:
            return Response(
                {"error": "node_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            node = MeshtasticNode.objects.get(node_id=node_id)
        except MeshtasticNode.DoesNotExist:
            return Response(
                {"error": f"Node with ID {node_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the node belongs to the same constellation as the API key
        if node.constellation != api_key.constellation:
            return Response(
                {
                    "error": f"Node does not belong to the same constellation as the API key"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if the node is already linked to this API key
        if NodeAuth.objects.filter(api_key=api_key, node=node).exists():
            return Response(
                {"error": f"Node is already linked to this API key"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Link the node to the API key
        NodeAuth.objects.create(api_key=api_key, node=node)

        return Response(
            {"success": f"Node added to API key"}, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def remove_node(self, request, pk=None):
        """
        Remove a node from an API key.
        """
        api_key = self.get_object()
        node_id = request.data.get("node_id")

        if not node_id:
            return Response(
                {"error": "node_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            node = MeshtasticNode.objects.get(node_id=node_id)
        except MeshtasticNode.DoesNotExist:
            return Response(
                {"error": f"Node with ID {node_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the node is linked to this API key
        link = NodeAuth.objects.filter(api_key=api_key, node=node).first()
        if not link:
            return Response(
                {"error": f"Node is not linked to this API key"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Remove the link
        link.delete()

        return Response(
            {"success": f"Node removed from API key"}, status=status.HTTP_200_OK
        )


class ObservedNodeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing observed nodes.
    """

    queryset = ObservedNode.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filter nodes based on user permissions.
        """
        user = self.request.user
        return ObservedNode.objects.filter(
            constellation__memberships__user=user,
            constellation__memberships__role__in=["admin", "editor"],
        ).distinct()

    def perform_create(self, serializer):
        """
        Create a new node and ensure the user has proper permissions.
        """
        constellation = serializer.validated_data["constellation"]

        # Check if user has permission to add nodes to this constellation
        if not ConstellationUserMembership.objects.filter(
            user=self.request.user,
            constellation=constellation,
            role__in=["admin", "editor"],
        ).exists():
            raise permissions.PermissionDenied(
                "You don't have permission to add nodes to this constellation."
            )

        serializer.save()

    @action(detail=True, methods=["post"])
    def add_api_key(self, request, pk=None):
        """
        Add an API key to a node.
        """
        node = self.get_object()
        api_key_id = request.data.get("api_key_id")

        if not api_key_id:
            return Response(
                {"error": "api_key_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            api_key = NodeAPIKey.objects.get(id=api_key_id)
        except NodeAPIKey.DoesNotExist:
            return Response(
                {"error": f"API key with ID {api_key_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the API key is already linked to this node
        if NodeAuth.objects.filter(api_key=api_key, node=node).exists():
            return Response(
                {"error": f"API key is already linked to this node"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Link the API key to the node
        NodeAuth.objects.create(api_key=api_key, node=node)

        return Response(
            {"success": f"API key added to node"}, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def remove_api_key(self, request, pk=None):
        """
        Remove an API key from a node.
        """
        node = self.get_object()
        api_key_id = request.data.get("api_key_id")

        if not api_key_id:
            return Response(
                {"error": "api_key_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            api_key = NodeAPIKey.objects.get(id=api_key_id)
        except NodeAPIKey.DoesNotExist:
            return Response(
                {"error": f"API key with ID {api_key_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the API key is linked to this node
        link = NodeAuth.objects.filter(api_key=api_key, node=node).first()
        if not link:
            return Response(
                {"error": f"API key is not linked to this node"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Remove the link
        link.delete()

        return Response(
            {"success": f"API key removed from node"}, status=status.HTTP_200_OK
        )


class ManagedNodeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing owned nodes.
    """

    queryset = ManagedNode.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filter nodes based on user ownership.
        """
        user = self.request.user
        return ManagedNode.objects.filter(owner=user)

    def perform_create(self, serializer):
        """
        Create a new managed node and set the owner.
        """
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["post"])
    def add_api_key(self, request, pk=None):
        """
        Add an API key to a managed node.
        """
        node = self.get_object()
        api_key_id = request.data.get("api_key_id")

        if not api_key_id:
            return Response(
                {"error": "api_key_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            api_key = NodeAPIKey.objects.get(id=api_key_id)
        except NodeAPIKey.DoesNotExist:
            return Response(
                {"error": f"API key with ID {api_key_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the API key is already linked to this node
        if NodeAuth.objects.filter(api_key=api_key, node=node).exists():
            return Response(
                {"error": f"API key is already linked to this node"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Link the API key to the node
        NodeAuth.objects.create(api_key=api_key, node=node)

        return Response(
            {"success": f"API key added to node"}, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def remove_api_key(self, request, pk=None):
        """
        Remove an API key from a managed node.
        """
        node = self.get_object()
        api_key_id = request.data.get("api_key_id")

        if not api_key_id:
            return Response(
                {"error": "api_key_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            api_key = NodeAPIKey.objects.get(id=api_key_id)
        except NodeAPIKey.DoesNotExist:
            return Response(
                {"error": f"API key with ID {api_key_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the API key is linked to this node
        link = NodeAuth.objects.filter(api_key=api_key, node=node).first()
        if not link:
            return Response(
                {"error": f"API key is not linked to this node"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Remove the link
        link.delete()

        return Response(
            {"success": f"API key removed from node"}, status=status.HTTP_200_OK
        )
