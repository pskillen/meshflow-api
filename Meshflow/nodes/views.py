import re
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import (
    BooleanField,
    Case,
    Count,
    DateTimeField,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from common.mesh_node_helpers import meshtastic_hex_to_int
from constellations.models import ConstellationUserMembership
from nodes.constants import INFRASTRUCTURE_ROLES
from nodes.models import (
    DeviceMetrics,
    EnvironmentExposure,
    EnvironmentMetrics,
    ManagedNode,
    ManagedNodeStatus,
    NodeAPIKey,
    NodeAuth,
    NodeLatestStatus,
    NodeOwnerClaim,
    NodeRfProfile,
    NodeRfPropagationRender,
    ObservedNode,
    Position,
    PowerMetrics,
    RoleSource,
    WeatherUse,
)
from nodes.permission_helpers import (
    user_can_edit_observed_node_environment_settings,
    user_can_edit_observed_node_rf_profile,
)
from nodes.serializers import (
    APIKeyCreateSerializer,
    APIKeyDetailSerializer,
    APIKeySerializer,
    DeviceMetricsBulkSerializer,
    DeviceMetricsSerializer,
    EnvironmentMetricsBulkSerializer,
    EnvironmentMetricsSerializer,
    ManagedNodeSerializer,
    NodeOwnerClaimSerializer,
    NodeRfProfileSerializer,
    NodeRfProfileUpdateSerializer,
    NodeRfPropagationRenderSerializer,
    ObservedNodeEnvironmentSettingsSerializer,
    ObservedNodeSearchSerializer,
    ObservedNodeSerializer,
    OwnedManagedNodeSerializer,
    PositionSerializer,
    PowerMetricsSerializer,
)
from nodes.services.device_metrics import get_device_metrics_bulk
from nodes.services.environment_metrics import get_environment_metrics_bulk
from packets.models import PacketObservation

from .utils import generate_claim_key


def _multi_query_strings(request, name):
    """Collect repeated or comma-separated query values for `name`."""
    out = []
    for raw in request.query_params.getlist(name):
        for part in raw.split(","):
            p = part.strip()
            if p:
                out.append(p)
    return out


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
            node = ManagedNode.objects.get(node_id=node_id, deleted_at__isnull=True)
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
            node = ManagedNode.objects.get(node_id=node_id, deleted_at__isnull=True)
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
        qs = (
            ObservedNode.objects.all()
            .order_by("-last_heard", "node_id")
            .select_related(
                "latest_status",
                "monitoring_config",
                "mesh_presence",
            )
        )
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

        from traceroute_analytics.neo4j_service import run_node_links_query

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
            .select_related("latest_status", "monitoring_config", "mesh_presence")
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

    @action(detail=False, methods=["get"], url_path="weather")
    def weather(self, request):
        """
        Get observed nodes that have reported environment metrics within the cutoff.

        Query params: environment_reported_after (ISO 8601, default 24h ago), page, page_size
        """
        default_cutoff = timezone.now() - timedelta(hours=24)
        environment_reported_after = request.query_params.get("environment_reported_after")
        if environment_reported_after:
            try:
                cutoff = timezone.datetime.fromisoformat(environment_reported_after.replace("Z", "+00:00"))
                if timezone.is_naive(cutoff):
                    cutoff = timezone.make_aware(cutoff)
            except ValueError, TypeError:
                cutoff = default_cutoff
        else:
            cutoff = default_cutoff

        qs = (
            ObservedNode.objects.filter(
                latest_status__environment_reported_time__isnull=False,
                latest_status__environment_reported_time__gte=cutoff,
            )
            .order_by("-latest_status__environment_reported_time", "node_id")
            .select_related("latest_status")
        )

        weather_use_labels = _multi_query_strings(request, "weather_use")
        if weather_use_labels:
            w_map = {w.label: w.value for w in WeatherUse}
            try:
                w_vals = [w_map[label] for label in weather_use_labels]
            except KeyError:
                return Response(
                    {"error": "Invalid weather_use; use unknown, include, or exclude."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(weather_use__in=w_vals)

        exposure_labels = _multi_query_strings(request, "environment_exposure")
        if exposure_labels:
            e_map = {e.label: e.value for e in EnvironmentExposure}
            try:
                e_vals = [e_map[label] for label in exposure_labels]
            except KeyError:
                return Response(
                    {"error": "Invalid environment_exposure; use unknown, indoor, outdoor, or sheltered."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(environment_exposure__in=e_vals)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="environment-settings")
    def environment_settings(self, request, node_id=None):
        """Update environment_exposure and/or weather_use (staff or claim owner only)."""
        node = self.get_object()
        if not user_can_edit_observed_node_environment_settings(request.user, node):
            raise PermissionDenied()
        ser = ObservedNodeEnvironmentSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        update_fields = []
        if "environment_exposure" in vd:
            node.environment_exposure = next(
                c.value for c in EnvironmentExposure if c.label == vd["environment_exposure"]
            )
            update_fields.append("environment_exposure")
        if "weather_use" in vd:
            node.weather_use = next(c.value for c in WeatherUse if c.label == vd["weather_use"])
            update_fields.append("weather_use")
        node.save(update_fields=update_fields)
        out = ObservedNodeSerializer(node, context=self.get_serializer_context())
        return Response(out.data)

    @action(detail=True, methods=["get", "patch"], url_path="rf-profile")
    def rf_profile(self, request, node_id=None):
        """Read or update RF propagation profile (coordinates owner/staff only in serializer)."""
        node = self.get_object()
        if request.method == "GET":
            try:
                profile = node.rf_profile
            except NodeRfProfile.DoesNotExist:
                return Response(status=status.HTTP_204_NO_CONTENT)
            ser = NodeRfProfileSerializer(profile, context=self.get_serializer_context())
            return Response(ser.data)
        if not user_can_edit_observed_node_rf_profile(request.user, node):
            raise PermissionDenied()
        profile, _ = NodeRfProfile.objects.get_or_create(observed_node=node)
        ser = NodeRfProfileUpdateSerializer(
            data=request.data,
            partial=True,
            context={**self.get_serializer_context(), "profile": profile},
        )
        ser.is_valid(raise_exception=True)
        for attr, value in ser.validated_data.items():
            setattr(profile, attr, value)
        profile.save()
        return Response(NodeRfProfileSerializer(profile, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get"], url_path="rf-propagation")
    def rf_propagation(self, request, node_id=None):
        """Return latest RF propagation render row, or ``status: none`` when none exist."""
        node = self.get_object()
        render = node.latest_rf_render()
        if render is None:
            return Response({"status": "none"})
        ser = NodeRfPropagationRenderSerializer(render, context=self.get_serializer_context())
        return Response(ser.data)

    @action(detail=True, methods=["post"], url_path="rf-propagation/dismiss")
    def rf_propagation_dismiss(self, request, node_id=None):
        """Delete every non-``ready`` render row for this node.

        Powers the UI "Cancel" (while ``pending``/``running``) and "Dismiss"
        (while ``failed``) actions — the same discard semantics, one DELETE
        endpoint. ``ready`` rows are preserved so the currently-served map
        keeps working until the operator queues a fresh render.

        The worker is resilient to the row vanishing mid-flight: it catches
        ``DoesNotExist`` on pickup/status-check and returns without writing.
        """
        node = self.get_object()
        if not user_can_edit_observed_node_rf_profile(request.user, node):
            raise PermissionDenied()

        deleted, _ = (
            NodeRfPropagationRender.objects.filter(observed_node=node)
            .exclude(status=NodeRfPropagationRender.Status.READY)
            .delete()
        )
        return Response({"deleted": deleted}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="rf-propagation/cancel")
    def rf_propagation_cancel(self, request, node_id=None):
        """Mark any in-flight (``pending``/``running``) renders for this node as failed.

        Lets the user abandon a stuck render so the next ``recompute`` starts
        fresh. The worker picks up the status flip on its next DB read and
        bails without writing an asset (see ``render_rf_propagation``).
        """
        node = self.get_object()
        if not user_can_edit_observed_node_rf_profile(request.user, node):
            raise PermissionDenied()

        cancelled = NodeRfPropagationRender.objects.filter(
            observed_node=node,
            status__in=[
                NodeRfPropagationRender.Status.PENDING,
                NodeRfPropagationRender.Status.RUNNING,
            ],
        ).update(
            status=NodeRfPropagationRender.Status.FAILED,
            error_message="Cancelled by user",
            completed_at=timezone.now(),
        )
        return Response({"cancelled": cancelled}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="rf-propagation/recompute")
    def rf_propagation_recompute(self, request, node_id=None):
        """Queue a new propagation render.

        Dedup strategy:

        1. If a ``ready`` render with a matching content hash already exists
           (and its PNG is still on disk), reuse it — no new row.
        2. Else if a ``pending``/``running`` render exists for this node,
           return that row without enqueueing another task.
        3. Otherwise create a new ``pending`` row and dispatch the Celery
           task.
        """
        node = self.get_object()
        if not user_can_edit_observed_node_rf_profile(request.user, node):
            raise PermissionDenied()

        try:
            profile = node.rf_profile
        except NodeRfProfile.DoesNotExist:
            return Response(
                {"detail": "Set an RF profile before requesting a propagation render."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Compute hash + radius up front so cache lookup and eventual task agree.
        from rf_propagation.hashing import compute_input_hash
        from rf_propagation.payload import InvalidProfileError, build_request, hash_extras_from_payload
        from rf_propagation.tasks import render_rf_propagation

        try:
            payload = build_request(profile)
        except InvalidProfileError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        input_hash = compute_input_hash(profile, extras=hash_extras_from_payload(payload))

        asset_dir = Path(settings.RF_PROPAGATION_ASSET_DIR)
        cache_hit = (
            NodeRfPropagationRender.objects.filter(
                status=NodeRfPropagationRender.Status.READY,
                input_hash=input_hash,
            )
            .order_by("-created_at")
            .first()
        )
        if cache_hit is not None and cache_hit.asset_filename:
            if (asset_dir / cache_hit.asset_filename).is_file():
                if cache_hit.observed_node_id == node.pk:
                    ser = NodeRfPropagationRenderSerializer(cache_hit, context=self.get_serializer_context())
                    return Response(ser.data, status=status.HTTP_200_OK)
                row = NodeRfPropagationRender.objects.create(
                    observed_node=node,
                    status=NodeRfPropagationRender.Status.READY,
                    input_hash=input_hash,
                    asset_filename=cache_hit.asset_filename,
                    bounds_west=cache_hit.bounds_west,
                    bounds_south=cache_hit.bounds_south,
                    bounds_east=cache_hit.bounds_east,
                    bounds_north=cache_hit.bounds_north,
                    completed_at=timezone.now(),
                )
                ser = NodeRfPropagationRenderSerializer(row, context=self.get_serializer_context())
                return Response(ser.data, status=status.HTTP_201_CREATED)

        in_flight = (
            NodeRfPropagationRender.objects.filter(
                observed_node=node,
                status__in=[
                    NodeRfPropagationRender.Status.PENDING,
                    NodeRfPropagationRender.Status.RUNNING,
                ],
            )
            .order_by("-created_at")
            .first()
        )
        if in_flight is not None:
            ser = NodeRfPropagationRenderSerializer(in_flight, context=self.get_serializer_context())
            return Response(ser.data, status=status.HTTP_200_OK)

        row = NodeRfPropagationRender.objects.create(
            observed_node=node,
            status=NodeRfPropagationRender.Status.PENDING,
            input_hash=input_hash,
        )
        render_rf_propagation.delay(row.pk)
        ser = NodeRfPropagationRenderSerializer(row, context=self.get_serializer_context())
        return Response(ser.data, status=status.HTTP_201_CREATED)


class RfPropagationAssetView(APIView):
    """
    Serve a cached propagation PNG from disk (public; hash in filename is the secret).

    Returns 404 when the worker has not written the asset yet.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, node_id, filename):
        _ = node_id  # reserved for future per-node asset validation
        if ".." in filename or "/" in filename or "\\" in filename:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.png\Z", filename):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        base = Path(settings.RF_PROPAGATION_ASSET_DIR).resolve()
        target = (base / filename).resolve()
        try:
            target.relative_to(base)
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        if not target.is_file():
            raise Http404()
        response = FileResponse(target.open("rb"), content_type="image/png")
        response["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


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


class EnvironmentMetricsBulkView(APIView):
    """
    Bulk environment metrics for multiple nodes in one request.
    Used by Weather page for mini charts.
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
        metrics = get_environment_metrics_bulk(node_ids, start_date, end_date)
        serializer = EnvironmentMetricsBulkSerializer(metrics, many=True)
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
        metrics = get_environment_metrics_bulk(node_ids, start_date, end_date)
        serializer = EnvironmentMetricsBulkSerializer(metrics, many=True)
        return Response({"results": serializer.data})


class ManagedNodeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing managed nodes.
    """

    queryset = ManagedNode.objects.filter(deleted_at__isnull=True).order_by("node_id")
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ManagedNodeSerializer
    lookup_field = "node_id"

    def _status_requested(self):
        include_values = _multi_query_strings(self.request, "include")
        return "status" in {value.lower() for value in include_values}

    def _geo_classification_requested(self):
        include_values = _multi_query_strings(self.request, "include")
        return "geo_classification" in {value.lower() for value in include_values}

    def _annotate_common_fields(self, queryset):
        observed_node_qs = ObservedNode.objects.filter(node_id=OuterRef("node_id"))
        latest_status_qs = NodeLatestStatus.objects.filter(node__node_id=OuterRef("node_id"))
        return queryset.annotate(
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

    def _annotate_status_fields(self, queryset):
        now = timezone.now()
        hour_cutoff = now - timedelta(hours=1)
        day_cutoff = now - timedelta(hours=24)

        packet_observation_qs = PacketObservation.objects.filter(observer_id=OuterRef("pk"))
        observed_node_qs = ObservedNode.objects.filter(node_id=OuterRef("node_id"))

        status_qs = ManagedNodeStatus.objects.filter(node_id=OuterRef("pk"))
        last_packet_subquery = status_qs.values("last_packet_ingested_at")[:1]
        is_sending_subquery = Subquery(
            status_qs.values("is_sending_data")[:1],
            output_field=BooleanField(),
        )
        packets_last_hour_subquery = (
            packet_observation_qs.filter(upload_time__gte=hour_cutoff)
            .values("observer")
            .annotate(c=Count("id"))
            .values("c")[:1]
        )
        packets_last_24h_subquery = (
            packet_observation_qs.filter(upload_time__gte=day_cutoff)
            .values("observer")
            .annotate(c=Count("id"))
            .values("c")[:1]
        )

        return queryset.annotate(
            last_packet_ingested_at=Subquery(last_packet_subquery, output_field=DateTimeField()),
            packets_last_hour=Coalesce(
                Subquery(packets_last_hour_subquery, output_field=IntegerField()),
                Value(0),
            ),
            packets_last_24h=Coalesce(
                Subquery(packets_last_24h_subquery, output_field=IntegerField()),
                Value(0),
            ),
            radio_last_heard=Subquery(observed_node_qs.values("last_heard")[:1], output_field=DateTimeField()),
            is_eligible_traceroute_source=Case(
                When(allow_auto_traceroute=True, then=Coalesce(is_sending_subquery, Value(False))),
                default=Value(False),
                output_field=BooleanField(),
            ),
        )

    def _managed_nodes_queryset(self, owner=None):
        queryset = ManagedNode.objects.filter(deleted_at__isnull=True).order_by("node_id")
        if owner is not None:
            queryset = queryset.filter(owner=owner)
        queryset = self._annotate_common_fields(queryset)
        if self._status_requested():
            queryset = self._annotate_status_fields(queryset)
        return queryset

    def get_queryset(self):
        """Filter nodes based on user ownership and annotate with observed node and NodeLatestStatus."""
        return self._managed_nodes_queryset()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_status"] = self._status_requested()
        context["include_geo_classification"] = self._geo_classification_requested()
        return context

    def get_serializer_class(self):
        """Return different serializers based on the action."""
        if self.action in ("mine", "create", "update", "partial_update"):
            return OwnedManagedNodeSerializer
        return ManagedNodeSerializer

    def _managed_node_mutate_allowed(self, managed_node):
        user = self.request.user
        if user.is_staff or managed_node.owner_id == user.id:
            return
        self.permission_denied(
            self.request,
            message="You do not have permission to modify this managed node.",
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        context = self.get_serializer_context()
        if request.user.is_staff or instance.owner_id == request.user.id:
            serializer = OwnedManagedNodeSerializer(instance, context=context)
        else:
            serializer = ManagedNodeSerializer(instance, context=context)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Create a new managed node and set the owner."""
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        self._managed_node_mutate_allowed(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._managed_node_mutate_allowed(instance)
        now = timezone.now()
        NodeAuth.objects.filter(node=instance).delete()
        instance.deleted_at = now
        instance.save(update_fields=["deleted_at"])

    @action(detail=False, methods=["get"])
    def mine(self, request):
        """
        Get all managed nodes owned by the current user.
        """
        nodes = self._managed_nodes_queryset(owner=request.user)

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
        with transaction.atomic():
            claim.delete()
            if node.claimed_by_id == request.user.id:
                node.claimed_by = None
                node.save(update_fields=["claimed_by"])
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
