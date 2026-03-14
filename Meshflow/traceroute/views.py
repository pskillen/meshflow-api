"""Views for traceroute list, detail, and trigger."""

from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from constellations.models import ConstellationUserMembership
from nodes.models import ManagedNode, NodeOwnerClaim, ObservedNode

from .models import AutoTraceRoute
from .permissions import CanTriggerTraceroute
from .serializers import AutoTraceRouteSerializer, TracerouteListSerializer, TriggerTracerouteSerializer
from .target_selection import pick_traceroute_target

# Firmware enforces ~30s minimum between traceroutes per node. Reject requests within this window.
# set to 60 seconds to prevent spamming the network
TR_MIN_INTERVAL_SEC = 60


class TraceroutePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def traceroute_list(request):
    """List AutoTraceRoute with filters. All authenticated users."""
    qs = AutoTraceRoute.objects.select_related(
        "source_node__constellation",
        "target_node__latest_status",
        "triggered_by",
        "raw_packet",
    ).order_by("-triggered_at")

    managed_node = request.query_params.get("managed_node")
    if managed_node:
        try:
            mn = ManagedNode.objects.get(node_id=int(managed_node))
            qs = qs.filter(source_node=mn)
        except ValueError, ManagedNode.DoesNotExist:
            pass

    source_node = request.query_params.get("source_node")
    if source_node:
        try:
            mn = ManagedNode.objects.get(node_id=int(source_node))
            qs = qs.filter(source_node=mn)
        except ValueError, ManagedNode.DoesNotExist:
            pass

    target_node = request.query_params.get("target_node")
    if target_node:
        try:
            on = ObservedNode.objects.get(node_id=int(target_node))
            qs = qs.filter(target_node=on)
        except ValueError, ObservedNode.DoesNotExist:
            pass

    status_filter = request.query_params.get("status")
    if status_filter:
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
        if statuses:
            qs = qs.filter(status__in=statuses)

    trigger_type = request.query_params.get("trigger_type")
    if trigger_type:
        qs = qs.filter(trigger_type=trigger_type)

    triggered_after = request.query_params.get("triggered_after")
    if triggered_after:
        try:
            from django.utils.dateparse import parse_datetime

            dt = parse_datetime(triggered_after)
            if dt:
                qs = qs.filter(triggered_at__gte=dt)
        except ValueError, TypeError:
            pass

    triggered_before = request.query_params.get("triggered_before")
    if triggered_before:
        try:
            from django.utils.dateparse import parse_datetime

            dt = parse_datetime(triggered_before)
            if dt:
                qs = qs.filter(triggered_at__lte=dt)
        except ValueError, TypeError:
            pass

    paginator = TraceroutePagination()
    page = paginator.paginate_queryset(qs, request)

    # Bulk-fetch for list view to avoid N+1
    source_node_ids = list({item.source_node.node_id for item in page if item.source_node})
    observed_short_names = {}
    if source_node_ids:
        for row in ObservedNode.objects.filter(node_id__in=source_node_ids).values("node_id", "short_name"):
            observed_short_names[row["node_id"]] = row["short_name"]

    all_route_node_ids = set()
    for item in page:
        if item.route:
            all_route_node_ids.update(x["node_id"] for x in item.route)
        if item.route_back:
            all_route_node_ids.update(x["node_id"] for x in item.route_back)
    all_route_node_ids.discard(0xFFFFFFFF)
    observed_by_id = {}
    if all_route_node_ids:
        for o in ObservedNode.objects.filter(node_id__in=all_route_node_ids).select_related("latest_status"):
            observed_by_id[o.node_id] = o

    target_node_pks = list({item.target_node_id for item in page if item.target_node})
    user_claims_by_node = {}
    if target_node_pks and request.user.is_authenticated:
        for c in NodeOwnerClaim.objects.filter(node_id__in=target_node_pks, user=request.user):
            user_claims_by_node[c.node_id] = c

    serializer_context = {
        "request": request,
        "observed_short_names": observed_short_names,
        "observed_by_id": observed_by_id,
        "user_claims_by_node": user_claims_by_node,
    }
    serializer = TracerouteListSerializer(page, many=True, context=serializer_context)
    return paginator.get_paginated_response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def traceroute_detail(request, pk):
    """Single AutoTraceRoute. All authenticated users."""
    obj = get_object_or_404(
        AutoTraceRoute.objects.select_related(
            "source_node", "target_node__latest_status", "triggered_by", "raw_packet"
        ),
        pk=pk,
    )
    serializer = AutoTraceRouteSerializer(obj)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanTriggerTraceroute])
def traceroute_trigger(request):
    """Manual trigger. Admin/editor only."""
    serializer = TriggerTracerouteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    managed_node_id = serializer.validated_data["managed_node_id"]
    target_node_id = serializer.validated_data.get("target_node_id")

    try:
        source_node = ManagedNode.objects.get(node_id=managed_node_id)
    except ManagedNode.DoesNotExist:
        return Response(
            {"managed_node_id": ["ManagedNode with this node_id not found."]},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not source_node.allow_auto_traceroute:
        return Response(
            {"detail": "This managed node does not allow traceroutes (allow_auto_traceroute is disabled)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Rate limit: firmware enforces ~30s between traceroutes per node
    last_tr = (
        AutoTraceRoute.objects.filter(source_node=source_node).order_by("-triggered_at").values("triggered_at").first()
    )
    if last_tr:
        cutoff = timezone.now() - timedelta(seconds=TR_MIN_INTERVAL_SEC)
        if last_tr["triggered_at"] > cutoff:
            next_allowed = last_tr["triggered_at"] + timedelta(seconds=TR_MIN_INTERVAL_SEC)
            remaining = max(0, (next_allowed - timezone.now()).total_seconds())
            return Response(
                {
                    "detail": f"Traceroute rate limited. "
                    f"This node's last traceroute was less than {TR_MIN_INTERVAL_SEC}s ago. "
                    f"Try again in {int(remaining)}s."
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

    # Check constellation permission (CanTriggerTraceroute allows staff; for non-staff check membership)
    if not request.user.is_staff:
        has_perm = ConstellationUserMembership.objects.filter(
            user=request.user,
            constellation=source_node.constellation,
            role__in=["admin", "editor"],
        ).exists()
        if not has_perm:
            return Response(
                {"detail": "You do not have permission to trigger traceroutes for this node's constellation."},
                status=status.HTTP_403_FORBIDDEN,
            )

    if target_node_id is not None:
        try:
            target_node = ObservedNode.objects.get(node_id=target_node_id)
        except ObservedNode.DoesNotExist:
            return Response(
                {"target_node_id": ["ObservedNode with this node_id not found."]},
                status=status.HTTP_404_NOT_FOUND,
            )
    else:
        target_node = pick_traceroute_target(source_node)
        if not target_node:
            return Response(
                {"detail": "No ObservedNode available for auto-selection. " "Specify target_node_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    auto_tr = AutoTraceRoute.objects.create(
        source_node=source_node,
        target_node=target_node,
        trigger_type=AutoTraceRoute.TRIGGER_TYPE_USER,
        triggered_by=request.user,
        trigger_source=None,
        status=AutoTraceRoute.STATUS_PENDING,
    )

    # Send command via channel layer
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"node_{source_node.node_id}",
        {"type": "node_command", "command": {"type": "traceroute", "target": target_node.node_id}},
    )

    auto_tr.status = AutoTraceRoute.STATUS_SENT
    auto_tr.save(update_fields=["status"])

    serializer = AutoTraceRouteSerializer(auto_tr)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def heatmap_edges(request):
    """Aggregated traceroute edges and nodes for heatmap visualization. Queries Neo4j."""
    from django.utils.dateparse import parse_datetime

    from .neo4j_service import run_heatmap_query

    triggered_at_after = None
    if request.query_params.get("triggered_at_after"):
        dt = parse_datetime(request.query_params["triggered_at_after"])
        if dt:
            triggered_at_after = dt

    constellation_id = request.query_params.get("constellation_id")
    if constellation_id is not None:
        try:
            constellation_id = int(constellation_id)
        except ValueError:
            constellation_id = None

    bbox = None
    bbox_param = request.query_params.get("bbox")
    if bbox_param:
        parts = [p.strip() for p in bbox_param.split(",")]
        if len(parts) >= 4:
            try:
                bbox = [float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])]
            except ValueError:
                pass

    try:
        data = run_heatmap_query(
            triggered_at_after=triggered_at_after,
            bbox=bbox,
            constellation_id=constellation_id,
        )
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception("heatmap_edges: Neo4j query failed: %s", e)
        return Response(
            {"detail": "Failed to fetch heatmap data."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def traceroute_can_trigger(request):
    """Returns whether the current user can trigger traceroutes."""
    can = (
        request.user.is_staff
        or ConstellationUserMembership.objects.filter(
            user=request.user,
            role__in=["admin", "editor"],
        ).exists()
    )
    return Response({"can_trigger": can})
