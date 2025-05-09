from datetime import datetime

from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from common.mesh_node_helpers import meshtastic_hex_to_int
from constellations.models import ConstellationUserMembership
from nodes.models import DeviceMetrics, ManagedNode, NodeAPIKey, NodeAuth, NodeOwnerClaim, ObservedNode, Position
from nodes.serializers import (
    APIKeyCreateSerializer,
    APIKeyDetailSerializer,
    APIKeySerializer,
    DeviceMetricsSerializer,
    ManagedNodeSerializer,
    NodeOwnerClaimSerializer,
    ObservedNodeSearchSerializer,
    ObservedNodeSerializer,
    OwnedManagedNodeSerializer,
    PositionSerializer,
)

from .utils import generate_claim_key


class APIKeyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for API keys.

    Allows users to create, view, update, and delete API keys for constellations
    they have admin or editor access to.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = APIKeySerializer

    def get_queryset(self):
        """Filter API keys to only show those for constellations the user has access to."""
        user = self.request.user
        return NodeAPIKey.objects.filter(owner=user).distinct().order_by("id")

    def get_serializer_class(self):
        """Return different serializers based on the action."""
        if self.action == "create":
            return APIKeyCreateSerializer
        elif self.action in ["retrieve", "list"]:
            return APIKeyDetailSerializer
        return APIKeySerializer

    def perform_create(self, serializer):
        """Create a new API key and ensure the user has proper permissions."""
        constellation = serializer.validated_data["constellation"]

        # Check if user has permission to create API keys for this constellation
        if not ConstellationUserMembership.objects.filter(
            user=self.request.user,
            constellation=constellation,
            role__in=["admin", "editor"],
        ).exists():
            raise permissions.PermissionDenied("You don't have permission to create API keys for this constellation.")

        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["post"])
    def add_node(self, request, pk=None):
        """Add a node to an API key."""
        api_key = self.get_object()
        node_id = request.data.get("node_id")

        if not node_id:
            return Response({"error": "node_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            node = ManagedNode.objects.get(node_id=node_id)
        except ManagedNode.DoesNotExist:
            return Response(
                {"error": f"Node with ID {node_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the node belongs to the same constellation as the API key
        if node.constellation != api_key.constellation:
            return Response(
                {"error": "Node does not belong to the same constellation as the API key"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if the node is already linked to this API key
        if NodeAuth.objects.filter(api_key=api_key, node=node).exists():
            return Response(
                {"error": "Node is already linked to this API key"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Link the node to the API key
        NodeAuth.objects.create(api_key=api_key, node=node)

        return Response({"success": "Node added to API key"}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def remove_node(self, request, pk=None):
        """Remove a node from an API key."""
        api_key = self.get_object()
        node_id = request.data.get("node_id")

        if not node_id:
            return Response({"error": "node_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            node = ManagedNode.objects.get(node_id=node_id)
        except ManagedNode.DoesNotExist:
            return Response(
                {"error": f"Node with ID {node_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the node is linked to this API key
        link = NodeAuth.objects.filter(api_key=api_key, node=node).first()
        if not link:
            return Response(
                {"error": "Node is not linked to this API key"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Remove the link
        link.delete()

        return Response({"success": "Node removed from API key"}, status=status.HTTP_200_OK)


class ObservedNodeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing observed nodes.
    """

    queryset = ObservedNode.objects.all().order_by("node_id")
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ObservedNodeSerializer
    lookup_field = "node_id"

    def get_queryset(self):
        """Filter nodes based on user permissions."""
        return ObservedNode.objects.all().order_by("node_id")

    def perform_create(self, serializer):
        """Create a new node."""
        serializer.save()

    @action(detail=False, methods=["get"])
    def mine(self, request):
        """
        Get all observed nodes claimed by the current user.
        """
        nodes = ObservedNode.objects.filter(claimed_by=request.user).order_by("node_id")
        page = self.paginate_queryset(nodes)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(nodes, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        """
        Search for observed nodes by node_id_str, short_name, long_name, or node_id.

        Query parameters:
        - q: Search term to match against node_id_str, short_name, long_name, or node_id
        """
        query = request.query_params.get("q", "")
        if not query:
            return Response(
                {"error": "Search query parameter 'q' is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Initialize an empty Q object for our conditions
        conditions = Q()

        # Check if query is a node_id_str (hex format starting with !)
        if query.startswith("!") and len(query) == 9:
            try:
                # Convert hex node_id_str to integer node_id
                node_id = meshtastic_hex_to_int(query)
                conditions |= Q(node_id=node_id)
            except ValueError:
                # If conversion fails, just continue with other search methods
                pass
        else:
            conditions |= Q(node_id_str__icontains=query)

        # Try to convert query to integer for node_id search if it's numeric
        try:
            node_id_query = int(query)
            conditions |= Q(node_id=node_id_query)
        except (ValueError, TypeError):
            pass

        # Add conditions for text fields
        conditions |= Q(short_name__icontains=query)
        conditions |= Q(long_name__icontains=query)

        # Search for nodes matching the query
        nodes = ObservedNode.objects.filter(conditions).order_by("node_id")

        serializer = ObservedNodeSearchSerializer(nodes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def positions(self, request, node_id=None):
        """
        Get positions for a specific node with optional date filtering.

        Query parameters:
        - start_date: Filter positions after this date (format: YYYY-MM-DD)
        - end_date: Filter positions before this date (format: YYYY-MM-DD)
        """
        node = self.get_object()

        # Get query parameters
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        # Filter positions by node
        positions = Position.objects.filter(node=node).order_by("-reported_time")

        # Apply date filters if provided
        if start_date:
            try:
                start_datetime = timezone.datetime.strptime(start_date, "%Y-%m-%d")
                start_datetime = timezone.make_aware(start_datetime)
                positions = positions.filter(reported_time__gte=start_datetime)
            except ValueError:
                return Response(
                    {"error": "Invalid start_date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if end_date:
            try:
                end_datetime = timezone.datetime.strptime(end_date, "%Y-%m-%d")
                # Set time to end of day
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
                end_datetime = timezone.make_aware(end_datetime)
                positions = positions.filter(reported_time__lte=end_datetime)
            except ValueError:
                return Response(
                    {"error": "Invalid end_date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = PositionSerializer(positions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def device_metrics(self, request, node_id=None):
        """
        Get device metrics for a specific node with optional date filtering.

        Query parameters:
        - start_date: Filter metrics after this date (format: YYYY-MM-DD)
        - end_date: Filter metrics before this date (format: YYYY-MM-DD)
        """
        node = self.get_object()

        # Get query parameters
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        # Filter device metrics by node
        metrics = DeviceMetrics.objects.filter(node=node).order_by("-reported_time")

        # Apply date filters if provided
        if start_date:
            try:
                start_datetime = datetime.fromisoformat(start_date)
                metrics = metrics.filter(reported_time__gte=start_datetime)
            except ValueError:
                return Response(
                    {"error": "Invalid start_date format. Use YYYY-MM-DD or full ISO 8601 format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if end_date:
            try:
                end_datetime = datetime.fromisoformat(end_date)
                # Set time to end of day
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
                metrics = metrics.filter(reported_time__lte=end_datetime)
            except ValueError:
                return Response(
                    {"error": "Invalid end_date format. Use YYYY-MM-DD or full ISO 8601 format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = DeviceMetricsSerializer(metrics, many=True)
        return Response(serializer.data)


class ManagedNodeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing managed nodes.
    """

    queryset = ManagedNode.objects.all().order_by("node_id")
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ManagedNodeSerializer
    lookup_field = "node_id"

    def get_queryset(self):
        """Filter nodes based on user ownership and annotate with observed node and latest position info."""

        # Subquery for ObservedNode fields
        observed_node_qs = ObservedNode.objects.filter(node_id=OuterRef("node_id"))
        # Subquery for latest Position fields
        latest_position_qs = Position.objects.filter(node__node_id=OuterRef("node_id")).order_by("-reported_time")
        return (
            ManagedNode.objects.all()
            .order_by("node_id")
            .annotate(
                long_name=Subquery(observed_node_qs.values("long_name")[:1]),
                short_name=Subquery(observed_node_qs.values("short_name")[:1]),
                last_heard=Subquery(observed_node_qs.values("last_heard")[:1]),
                last_latitude=Subquery(latest_position_qs.values("latitude")[:1]),
                last_longitude=Subquery(latest_position_qs.values("longitude")[:1]),
            )
        )

    def get_serializer_class(self):
        """Return different serializers based on the action."""
        if self.action == "mine":
            return OwnedManagedNodeSerializer
        if self.action == "create":
            return OwnedManagedNodeSerializer
        return ManagedNodeSerializer

    def perform_create(self, serializer):
        """Create a new managed node and set the owner."""
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        """
        Get all managed nodes owned by the current user.
        """
        # Subquery for ObservedNode fields
        observed_node_qs = ObservedNode.objects.filter(node_id=OuterRef("node_id"))
        # Subquery for latest Position fields
        latest_position_qs = Position.objects.filter(node__node_id=OuterRef("node_id")).order_by("-reported_time")

        nodes = (
            ManagedNode.objects.filter(owner=request.user)
            .order_by("node_id")
            .annotate(
                long_name=Subquery(observed_node_qs.values("long_name")[:1]),
                short_name=Subquery(observed_node_qs.values("short_name")[:1]),
                last_heard=Subquery(observed_node_qs.values("last_heard")[:1]),
                last_latitude=Subquery(latest_position_qs.values("latitude")[:1]),
                last_longitude=Subquery(latest_position_qs.values("longitude")[:1]),
            )
        )

        page = self.paginate_queryset(nodes)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(nodes, many=True)
        return Response(serializer.data)


class ObservedNodeClaimView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, node_id):
        node = get_object_or_404(ObservedNode, node_id=node_id)
        claim = NodeOwnerClaim.objects.filter(node=node, user=request.user).first()
        if not claim:
            return Response({"detail": "No claim found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = NodeOwnerClaimSerializer(claim)
        return Response(serializer.data)

    def post(self, request, node_id):
        node = get_object_or_404(ObservedNode, node_id=node_id)
        if NodeOwnerClaim.objects.filter(node=node, user=request.user).exists():
            return Response({"detail": "Claim already exists."}, status=status.HTTP_400_BAD_REQUEST)
        claim_key = generate_claim_key()
        claim = NodeOwnerClaim.objects.create(node=node, user=request.user, claim_key=claim_key)
        serializer = NodeOwnerClaimSerializer(claim)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, node_id):
        node = get_object_or_404(ObservedNode, node_id=node_id)
        claim = NodeOwnerClaim.objects.filter(node=node, user=request.user).first()
        if not claim:
            return Response({"detail": "No claim found."}, status=status.HTTP_404_NOT_FOUND)
        claim.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserNodeClaimsView(APIView):
    """
    API endpoint to retrieve all NodeOwnerClaim models for the current user.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        Get all node claims for the current user.
        """
        claims = NodeOwnerClaim.objects.filter(user=request.user).select_related('node')
        serializer = NodeOwnerClaimSerializer(claims, many=True)
        return Response(serializer.data)
