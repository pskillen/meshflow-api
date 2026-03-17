from datetime import datetime, timedelta

from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from common.mesh_node_helpers import meshtastic_hex_to_int
from constellations.models import ConstellationUserMembership
from nodes.models import (
    DeviceMetrics,
    EnvironmentMetrics,
    ManagedNode,
    NodeAPIKey,
    NodeAuth,
    NodeLatestStatus,
    NodeOwnerClaim,
    ObservedNode,
    Position,
    PowerMetrics,
    RoleSource,
)
from nodes.serializers import (
    APIKeyCreateSerializer,
    APIKeyDetailSerializer,
    APIKeySerializer,
    DeviceMetricsBulkSerializer,
    DeviceMetricsSerializer,
    EnvironmentMetricsSerializer,
    ManagedNodeSerializer,
    NodeOwnerClaimSerializer,
    ObservedNodeSearchSerializer,
    ObservedNodeSerializer,
    OwnedManagedNodeSerializer,
    PositionSerializer,
    PowerMetricsSerializer,
)
from nodes.services.device_metrics import get_device_metrics_bulk

from .utils import generate_claim_key

# Infrastructure roles: ROUTER, ROUTER_CLIENT, REPEATER, ROUTER_LATE (optionally CLIENT_BASE)
INFRASTRUCTURE_ROLES = [RoleSource.ROUTER, RoleSource.ROUTER_CLIENT, RoleSource.REPEATER, RoleSource.ROUTER_LATE]


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
        """Filter nodes based on user permissions and prefetch latest status."""
        qs = ObservedNode.objects.all().order_by("-last_heard", "node_id").select_related("latest_status")
        # Apply last_heard_after filter only for list action
        if self.action == "list":
            last_heard_after = self.request.query_params.get("last_heard_after")
            if last_heard_after:
                try:
                    dt = timezone.datetime.fromisoformat(last_heard_after.replace("Z", "+00:00"))
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt)
                    qs = qs.filter(last_heard__gte=dt)
                except ValueError, TypeError:
                    pass
        return qs

    def perform_create(self, serializer):
        """Create a new node."""
        serializer.save()

    @action(detail=False, methods=["get"])
    def mine(self, request):
        """
        Get all observed nodes claimed by the current user.
        """
        nodes = ObservedNode.objects.filter(claimed_by=request.user).order_by("node_id").select_related("latest_status")

        page = self.paginate_queryset(nodes)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(nodes, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="recent_counts")
    def recent_counts(self, request):
        """
        Get node counts by time window (nodes seen since each threshold).

        Returns counts for: 2h, 24h, 7d, 30d, 90d, and all time.
        """
        now = timezone.now()
        windows = [
            ("2", now - timedelta(hours=2)),
            ("24", now - timedelta(hours=24)),
            ("168", now - timedelta(days=7)),
            ("720", now - timedelta(days=30)),
            ("2160", now - timedelta(days=90)),
        ]
        result = {}
        for key, threshold in windows:
            result[key] = ObservedNode.objects.filter(last_heard__gte=threshold).count()
        result["all"] = ObservedNode.objects.count()
        return Response(result)

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
        except ValueError, TypeError:
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

    @action(detail=True, methods=["get"], url_path="environment_metrics")
    def environment_metrics(self, request, node_id=None):
        """
        Get environment metrics for a specific node with optional date filtering.

        Query parameters:
        - start_date: Filter metrics after this date (format: YYYY-MM-DD)
        - end_date: Filter metrics before this date (format: YYYY-MM-DD)
        """
        node = self.get_object()
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        metrics = EnvironmentMetrics.objects.filter(node=node).order_by("-reported_time")

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
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
                metrics = metrics.filter(reported_time__lte=end_datetime)
            except ValueError:
                return Response(
                    {"error": "Invalid end_date format. Use YYYY-MM-DD or full ISO 8601 format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = EnvironmentMetricsSerializer(metrics, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="power_metrics")
    def power_metrics(self, request, node_id=None):
        """
        Get power metrics for a specific node with optional date filtering.

        Query parameters:
        - start_date: Filter metrics after this date (format: YYYY-MM-DD)
        - end_date: Filter metrics before this date (format: YYYY-MM-DD)
        """
        node = self.get_object()
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        metrics = PowerMetrics.objects.filter(node=node).order_by("-reported_time")

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
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
                metrics = metrics.filter(reported_time__lte=end_datetime)
            except ValueError:
                return Response(
                    {"error": "Invalid end_date format. Use YYYY-MM-DD or full ISO 8601 format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = PowerMetricsSerializer(metrics, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="traceroute-links")
    def traceroute_links(self, request, node_id=None):
        """
        Get traceroute links for this node from Neo4j.
        Returns edges (with avg SNR in/out), nodes, and snr_history per peer.

        Query parameters:
        - triggered_at_after: ISO 8601 datetime to filter edges
        """
        from django.utils.dateparse import parse_datetime

        from traceroute.neo4j_service import run_node_links_query

        node = self.get_object()
        nid = node.node_id

        triggered_at_after = None
        if request.query_params.get("triggered_at_after"):
            dt = parse_datetime(request.query_params.get("triggered_at_after"))
            if dt:
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt)
                triggered_at_after = dt

        try:
            result = run_node_links_query(nid, triggered_at_after=triggered_at_after)
            return Response(result)
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception("traceroute_links: Neo4j query failed: %s", e)
            return Response(
                {"detail": "Failed to fetch traceroute links."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @action(detail=False, methods=["get"], url_path="infrastructure")
    def infrastructure(self, request):
        """
        Get observed nodes whose role is infrastructure (router, repeater, etc.).

        Query params: last_heard_after, page, page_size, include_client_base (default false)
        """
        include_client_base = request.query_params.get("include_client_base", "false").lower() == "true"
        roles = INFRASTRUCTURE_ROLES + ([RoleSource.CLIENT_BASE] if include_client_base else [])

        qs = (
            ObservedNode.objects.filter(role__in=roles)
            .order_by("-last_heard", "node_id")
            .select_related("latest_status")
        )

        last_heard_after = request.query_params.get("last_heard_after")
        if last_heard_after:
            try:
                dt = timezone.datetime.fromisoformat(last_heard_after.replace("Z", "+00:00"))
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt)
                qs = qs.filter(last_heard__gte=dt)
            except ValueError, TypeError:
                pass

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class DeviceMetricsBulkView(APIView):
    """
    Bulk device metrics for multiple nodes in one request.
    Reusable by Infrastructure, Monitor, My Nodes pages.
    """

    permission_classes = [permissions.IsAuthenticated]

    def _parse_node_ids(self, request):
        """Extract node_ids from GET (comma-separated) or POST body."""
        if request.method == "GET":
            node_ids_param = request.query_params.get("node_ids", "")
            if not node_ids_param:
                return None
            try:
                return [int(x.strip()) for x in node_ids_param.split(",") if x.strip()]
            except ValueError:
                return None
        # POST
        node_ids = request.data.get("node_ids", [])
        if not isinstance(node_ids, list):
            return None
        try:
            return [int(x) for x in node_ids]
        except ValueError, TypeError:
            return None

    def _parse_date(self, value):
        """Parse ISO 8601 or YYYY-MM-DD date."""
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            return dt
        except ValueError:
            try:
                return timezone.datetime.strptime(str(value), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                return None

    def get(self, request):
        node_ids = self._parse_node_ids(request)
        if not node_ids:
            return Response(
                {"error": "node_ids query parameter required (comma-separated integers)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        start_date = self._parse_date(request.query_params.get("start_date"))
        end_date = self._parse_date(request.query_params.get("end_date"))
        metrics = get_device_metrics_bulk(node_ids, start_date, end_date)
        serializer = DeviceMetricsBulkSerializer(metrics, many=True)
        return Response({"results": serializer.data})

    def post(self, request):
        node_ids = self._parse_node_ids(request)
        if not node_ids:
            return Response(
                {"error": "node_ids required in body (array of integers)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        start_date = self._parse_date(request.data.get("start_date"))
        end_date = self._parse_date(request.data.get("end_date"))
        metrics = get_device_metrics_bulk(node_ids, start_date, end_date)
        serializer = DeviceMetricsBulkSerializer(metrics, many=True)
        return Response({"results": serializer.data})


class ManagedNodeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing managed nodes.
    """

    queryset = ManagedNode.objects.all().order_by("node_id")
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ManagedNodeSerializer
    lookup_field = "node_id"

    def get_queryset(self):
        """Filter nodes based on user ownership and annotate with observed node and NodeLatestStatus."""
        observed_node_qs = ObservedNode.objects.filter(node_id=OuterRef("node_id"))
        latest_status_qs = NodeLatestStatus.objects.filter(node__node_id=OuterRef("node_id"))

        return (
            ManagedNode.objects.all()
            .order_by("node_id")
            .annotate(
                long_name=Subquery(observed_node_qs.values("long_name")[:1]),
                short_name=Subquery(observed_node_qs.values("short_name")[:1]),
                last_heard=Subquery(observed_node_qs.values("last_heard")[:1]),
                last_latitude=Subquery(latest_status_qs.values("latitude")[:1]),
                last_longitude=Subquery(latest_status_qs.values("longitude")[:1]),
                last_altitude=Subquery(latest_status_qs.values("altitude")[:1]),
                last_position_time=Subquery(latest_status_qs.values("position_reported_time")[:1]),
                last_heading=Subquery(latest_status_qs.values("heading")[:1]),
                last_location_source=Subquery(latest_status_qs.values("location_source")[:1]),
                last_precision_bits=Subquery(latest_status_qs.values("precision_bits")[:1]),
                last_ground_speed=Subquery(latest_status_qs.values("ground_speed")[:1]),
                last_ground_track=Subquery(latest_status_qs.values("ground_track")[:1]),
                last_sats_in_view=Subquery(latest_status_qs.values("sats_in_view")[:1]),
                last_pdop=Subquery(latest_status_qs.values("pdop")[:1]),
                last_battery_level=Subquery(latest_status_qs.values("battery_level")[:1]),
                last_voltage=Subquery(latest_status_qs.values("voltage")[:1]),
                last_metrics_time=Subquery(latest_status_qs.values("metrics_reported_time")[:1]),
                last_channel_utilization=Subquery(latest_status_qs.values("channel_utilization")[:1]),
                last_air_util_tx=Subquery(latest_status_qs.values("air_util_tx")[:1]),
                last_uptime_seconds=Subquery(latest_status_qs.values("uptime_seconds")[:1]),
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
        observed_node_qs = ObservedNode.objects.filter(node_id=OuterRef("node_id"))
        latest_status_qs = NodeLatestStatus.objects.filter(node__node_id=OuterRef("node_id"))

        nodes = (
            ManagedNode.objects.filter(owner=request.user)
            .order_by("node_id")
            .annotate(
                long_name=Subquery(observed_node_qs.values("long_name")[:1]),
                short_name=Subquery(observed_node_qs.values("short_name")[:1]),
                last_heard=Subquery(observed_node_qs.values("last_heard")[:1]),
                last_latitude=Subquery(latest_status_qs.values("latitude")[:1]),
                last_longitude=Subquery(latest_status_qs.values("longitude")[:1]),
                last_altitude=Subquery(latest_status_qs.values("altitude")[:1]),
                last_position_time=Subquery(latest_status_qs.values("position_reported_time")[:1]),
                last_battery_level=Subquery(latest_status_qs.values("battery_level")[:1]),
                last_voltage=Subquery(latest_status_qs.values("voltage")[:1]),
                last_metrics_time=Subquery(latest_status_qs.values("metrics_reported_time")[:1]),
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
        if node.claimed_by_id and node.claimed_by_id != request.user.id:
            return Response(
                {"detail": "Node is already claimed by another user."},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
        claims = NodeOwnerClaim.objects.filter(user=request.user).select_related("node")
        serializer = NodeOwnerClaimSerializer(claims, many=True)
        return Response(serializer.data)
