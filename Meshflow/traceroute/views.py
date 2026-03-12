"""Views for traceroute list, detail, and trigger."""

from asgiref.sync import async_to_sync

from django.utils import timezone
from django.shortcuts import get_object_or_404

from channels.layers import get_channel_layer
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from constellations.models import ConstellationUserMembership
from nodes.models import ManagedNode, ObservedNode

from .models import AutoTraceRoute
from .permissions import CanTriggerTraceroute
from .serializers import AutoTraceRouteSerializer, TriggerTracerouteSerializer


class TraceroutePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def traceroute_list(request):
    """List AutoTraceRoute with filters. All authenticated users."""
    qs = AutoTraceRoute.objects.select_related(
        "source_node", "target_node", "triggered_by", "raw_packet"
    ).order_by("-triggered_at")

    managed_node = request.query_params.get("managed_node")
    if managed_node:
        try:
            mn = ManagedNode.objects.get(node_id=int(managed_node))
            qs = qs.filter(source_node=mn)
        except (ValueError, ManagedNode.DoesNotExist):
            pass

    source_node = request.query_params.get("source_node")
    if source_node:
        try:
            mn = ManagedNode.objects.get(node_id=int(source_node))
            qs = qs.filter(source_node=mn)
        except (ValueError, ManagedNode.DoesNotExist):
            pass

    target_node = request.query_params.get("target_node")
    if target_node:
        try:
            on = ObservedNode.objects.get(node_id=int(target_node))
            qs = qs.filter(target_node=on)
        except (ValueError, ObservedNode.DoesNotExist):
            pass

    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)

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
        except (ValueError, TypeError):
            pass

    triggered_before = request.query_params.get("triggered_before")
    if triggered_before:
        try:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(triggered_before)
            if dt:
                qs = qs.filter(triggered_at__lte=dt)
        except (ValueError, TypeError):
            pass

    paginator = TraceroutePagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = AutoTraceRouteSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def traceroute_detail(request, pk):
    """Single AutoTraceRoute. All authenticated users."""
    obj = get_object_or_404(AutoTraceRoute.objects.select_related("source_node", "target_node", "triggered_by", "raw_packet"), pk=pk)
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
        # Auto-select target: pick a recently-heard node from the same mesh (simplified: any ObservedNode)
        target_node = ObservedNode.objects.filter(last_heard__isnull=False).order_by("-last_heard").first()
        if not target_node:
            return Response(
                {"detail": "No ObservedNode available for auto-selection. Specify target_node_id."},
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
def traceroute_can_trigger(request):
    """Returns whether the current user can trigger traceroutes."""
    can = request.user.is_staff or ConstellationUserMembership.objects.filter(
        user=request.user,
        role__in=["admin", "editor"],
    ).exists()
    return Response({"can_trigger": can})
