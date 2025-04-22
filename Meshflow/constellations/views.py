from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import NodeAPIKey, NodeAuth, ConstellationUserMembership, Constellation
from .serializers import (
    APIKeySerializer,
    APIKeyDetailSerializer,
    APIKeyCreateSerializer,
    ConstellationSerializer,
)


class IsConstellationAdminOrEditor(permissions.BasePermission):
    """
    Permission to only allow admins or editors of a constellation to access its API keys.
    """

    def has_permission(self, request, view):
        # Allow GET requests for listing API keys
        if request.method in permissions.SAFE_METHODS:
            return True

        # For other methods, check if the user is an admin or editor of the constellation
        constellation_id = request.data.get('constellation')
        if not constellation_id:
            return False

        return ConstellationUserMembership.objects.filter(
            user=request.user,
            constellation_id=constellation_id,
            role__in=['admin', 'editor']
        ).exists()

    def has_object_permission(self, request, view, obj):
        # Check if the user is an admin or editor of the constellation
        if hasattr(obj, 'constellation'):
            constellation = obj.constellation
        else:
            constellation = obj

        return ConstellationUserMembership.objects.filter(
            user=request.user,
            constellation=constellation,
            role__in=['admin', 'editor']
        ).exists()


class ConstellationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for constellations.

    Allows users to create, view, update, and delete constellations
    they have access to.
    """

    serializer_class = ConstellationSerializer
    permission_classes = [permissions.IsAuthenticated, IsConstellationAdminOrEditor]

    def get_queryset(self):
        """
        Filter constellations to only show those the user is a member of.
        """
        user = self.request.user

        # Get the constellations the user is a member of
        constellation_ids = ConstellationUserMembership.objects.filter(
            user=user
        ).values_list('constellation_id', flat=True)

        # Return those constellations
        return Constellation.objects.filter(id__in=constellation_ids)

    def perform_create(self, serializer):
        """
        Create a new constellation and add the user as an admin.
        """
        constellation = serializer.save(created_by=self.request.user)

        # Add the user as an admin of the constellation
        ConstellationUserMembership.objects.create(
            user=self.request.user,
            constellation=constellation,
            role='admin'
        )


class APIKeyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for API keys.

    Allows users to create, view, update, and delete API keys for constellations
    they have admin or editor access to.
    """

    permission_classes = [permissions.IsAuthenticated, IsConstellationAdminOrEditor]

    def get_queryset(self):
        """
        Filter API keys to only show those for the specified constellation.
        """
        user = self.request.user
        constellation_id = self.kwargs.get('constellation_id')

        # Check if the user is a member of the constellation
        if not ConstellationUserMembership.objects.filter(
            user=user,
            constellation_id=constellation_id
        ).exists():
            return NodeAPIKey.objects.none()

        # Return API keys for the specified constellation
        return NodeAPIKey.objects.filter(constellation_id=constellation_id)

    def get_serializer_class(self):
        """
        Return different serializers based on the action.
        """
        if self.action == 'create':
            return APIKeyCreateSerializer
        elif self.action in ['retrieve', 'list']:
            return APIKeyDetailSerializer
        return APIKeySerializer

    def perform_create(self, serializer):
        """
        Create a new API key for the specified constellation.
        """
        constellation_id = self.kwargs.get('constellation_id')
        constellation = Constellation.objects.get(id=constellation_id)
        serializer.save(constellation=constellation, created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def add_node(self, request, pk=None):
        """
        Add a node to an API key.
        """
        api_key = self.get_object()
        node_id = request.data.get('node_id')

        if not node_id:
            return Response(
                {'error': 'node_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Import here to avoid circular imports
        from nodes.models import MeshtasticNode

        try:
            node = MeshtasticNode.objects.get(node_id=node_id)
        except MeshtasticNode.DoesNotExist:
            return Response(
                {'error': f'Node with ID {node_id} does not exist'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if the node is already linked to this API key
        if NodeAuth.objects.filter(api_key=api_key, node=node).exists():
            return Response(
                {'error': f'Node with ID {node_id} is already linked to this API key'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Link the node to the API key
        NodeAuth.objects.create(api_key=api_key, node=node)

        return Response(
            {'success': f'Node with ID {node_id} added to API key'},
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'])
    def remove_node(self, request, pk=None):
        """
        Remove a node from an API key.
        """
        api_key = self.get_object()
        node_id = request.data.get('node_id')

        if not node_id:
            return Response(
                {'error': 'node_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Import here to avoid circular imports
        from nodes.models import MeshtasticNode

        try:
            node = MeshtasticNode.objects.get(node_id=node_id)
        except MeshtasticNode.DoesNotExist:
            return Response(
                {'error': f'Node with ID {node_id} does not exist'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if the node is linked to this API key
        link = NodeAuth.objects.filter(api_key=api_key, node=node).first()
        if not link:
            return Response(
                {'error': f'Node with ID {node_id} is not linked to this API key'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Remove the link
        link.delete()

        return Response(
            {'success': f'Node with ID {node_id} removed from API key'},
            status=status.HTTP_200_OK
        )
