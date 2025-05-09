from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from django.db.models import Count, Q
from django.db.models.functions import Trunc

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from nodes.models import ManagedNode, ObservedNode
from packets.models import PacketObservation, RawPacket

from .serializers import GlobalStatsSerializer, NodeStatsSerializer


def parse_stats_params(request) -> Tuple[Optional[datetime], Optional[datetime], int, str]:
    """
    Parse common statistics parameters from the request.

    Args:
        request: The HTTP request

    Returns:
        Tuple of (start_date, end_date, interval, interval_type)

    Raises:
        ValueError: If parameters are invalid
    """
    # Get query parameters with defaults
    start_date = request.query_params.get("start_date")
    end_date = request.query_params.get("end_date")
    interval = int(request.query_params.get("interval", 1))
    interval_type = request.query_params.get("interval_type", "hour")

    # Validate interval type
    if interval_type not in ["hour", "day", "week", "month"]:
        raise ValueError("Invalid interval_type. Must be one of: hour, day, week, month")

    # Parse dates if provided
    parsed_start = None
    parsed_end = None

    if start_date:
        try:
            # Try parsing as ISO 8601 format first
            parsed_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            # Fall back to YYYY-MM-DD format for backward compatibility
            try:
                parsed_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                raise ValueError(
                    "Invalid start_date format. Must be ISO 8601 (YYYY-MM-DDTHH:MM:SS±HH:MM) or YYYY-MM-DD"
                )

    if end_date:
        try:
            # Try parsing as ISO 8601 format first
            parsed_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            # Fall back to YYYY-MM-DD format for backward compatibility
            try:
                parsed_end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                raise ValueError("Invalid end_date format. Must be ISO 8601 (YYYY-MM-DDTHH:MM:SS±HH:MM) or YYYY-MM-DD")

    return parsed_start, parsed_end, interval, interval_type


def get_interval_trunc_kwargs(interval_type: str, interval: int) -> Dict:
    """
    Get the truncation kwargs for the specified interval type and size.

    Args:
        interval_type: The type of interval (hour, day, week, month)
        interval: The size of the interval

    Returns:
        Dictionary of kwargs for Trunc function
    """
    # For hour intervals, we need to handle the special case of truncating to multiple hours
    if interval_type == "hour":
        return {"hour": interval}
    elif interval_type == "day":
        return {"day": interval}
    elif interval_type == "week":
        return {"week": interval}
    elif interval_type == "month":
        return {"month": interval}
    else:
        raise ValueError(f"Unsupported interval type: {interval_type}")


def get_interval_delta(interval_type: str, interval: int) -> timedelta:
    """
    Get a timedelta for the specified interval type and size.

    Args:
        interval_type: The type of interval (hour, day, week, month)
        interval: The size of the interval

    Returns:
        timedelta representing the interval
    """
    if interval_type == "hour":
        return timedelta(hours=interval)
    elif interval_type == "day":
        return timedelta(days=interval)
    elif interval_type == "week":
        return timedelta(weeks=interval)
    elif interval_type == "month":
        # Approximate month as 30 days
        return timedelta(days=30 * interval)
    else:
        raise ValueError(f"Unsupported interval type: {interval_type}")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def node_packet_stats(request, node_id: int):
    """
    Get packet statistics for a specific node over time intervals.

    Args:
        request: The HTTP request
        node_id: The ID of the node to get stats for

    Returns:
        Response containing packet statistics grouped by time intervals
    """
    try:
        # Validate node exists
        ObservedNode.objects.get(node_id=node_id)
    except ObservedNode.DoesNotExist:
        return Response({"status": "error", "message": "Node not found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        start_date, end_date, interval, interval_type = parse_stats_params(request)
    except ValueError as e:
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Build base query for packets from this node
    packets = RawPacket.objects.filter(from_int=node_id)

    # Apply date filters if provided
    if start_date:
        packets = packets.filter(first_reported_time__gte=start_date)
    if end_date:
        packets = packets.filter(first_reported_time__lt=end_date)

    # Get interval stats
    stats = (
        packets.annotate(
            interval_start=Trunc(
                "first_reported_time", interval_type, **get_interval_trunc_kwargs(interval_type, interval)
            )
        )
        .values("interval_start")
        .annotate(
            text_messages=Count("id", filter=Q(messagepacket__isnull=False)),
            position_updates=Count("id", filter=Q(positionpacket__isnull=False)),
            node_info=Count("id", filter=Q(nodeinfopacket__isnull=False)),
            device_metrics=Count("id", filter=Q(devicemetricspacket__isnull=False)),
            local_stats=Count("id", filter=Q(localstatspacket__isnull=False)),
            environment_metrics=Count("id", filter=Q(environmentmetricspacket__isnull=False)),
        )
        .order_by("interval_start")
    )

    # Format response
    intervals = []
    for stat in stats:
        interval_data = {
            "start_date": stat["interval_start"],
            "end_date": stat["interval_start"] + get_interval_delta(interval_type, interval),
            "packet_types": [
                {"packet_type": "text_message", "count": stat["text_messages"]},
                {"packet_type": "position", "count": stat["position_updates"]},
                {"packet_type": "node_info", "count": stat["node_info"]},
                {"packet_type": "device_metrics", "count": stat["device_metrics"]},
                {"packet_type": "local_stats", "count": stat["local_stats"]},
                {"packet_type": "environment_metrics", "count": stat["environment_metrics"]},
            ],
        }
        intervals.append(interval_data)

    response_data = {"start_date": start_date, "end_date": end_date, "intervals": intervals}

    # Validate and serialize response
    serializer = NodeStatsSerializer(data=response_data)
    if not serializer.is_valid():
        return Response(
            {"status": "error", "message": "Invalid response data"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response(serializer.validated_data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def node_received_stats(request, node_id: int):
    """
    Get statistics for packets received/heard by a specific node over time intervals.

    Args:
        request: The HTTP request
        node_id: The ID of the node to get stats for

    Returns:
        Response containing packet statistics grouped by time intervals
    """
    try:
        # Check if this is a managed node
        managed_node = ManagedNode.objects.get(node_id=node_id)
    except ManagedNode.DoesNotExist:
        # If not a managed node, return empty result
        return Response({"start_date": None, "end_date": None, "intervals": []}, status=status.HTTP_200_OK)

    try:
        start_date, end_date, interval, interval_type = parse_stats_params(request)
    except ValueError as e:
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Build base query for packet observations by this node
    observations = PacketObservation.objects.filter(observer=managed_node)

    # Apply date filters if provided
    if start_date:
        observations = observations.filter(rx_time__gte=start_date)
    if end_date:
        observations = observations.filter(rx_time__lt=end_date)

    # Get interval stats
    stats = (
        observations.annotate(
            interval_start=Trunc("rx_time", interval_type, **get_interval_trunc_kwargs(interval_type, interval))
        )
        .values("interval_start")
        .annotate(
            text_messages=Count("id", filter=Q(packet__messagepacket__isnull=False)),
            position_updates=Count("id", filter=Q(packet__positionpacket__isnull=False)),
            node_info=Count("id", filter=Q(packet__nodeinfopacket__isnull=False)),
            device_metrics=Count("id", filter=Q(packet__devicemetricspacket__isnull=False)),
            local_stats=Count("id", filter=Q(packet__localstatspacket__isnull=False)),
            environment_metrics=Count("id", filter=Q(packet__environmentmetricspacket__isnull=False)),
        )
        .order_by("interval_start")
    )

    # Format response
    intervals = []
    for stat in stats:
        interval_data = {
            "start_date": stat["interval_start"],
            "end_date": stat["interval_start"] + get_interval_delta(interval_type, interval),
            "packet_types": [
                {"packet_type": "text_message", "count": stat["text_messages"]},
                {"packet_type": "position", "count": stat["position_updates"]},
                {"packet_type": "node_info", "count": stat["node_info"]},
                {"packet_type": "device_metrics", "count": stat["device_metrics"]},
                {"packet_type": "local_stats", "count": stat["local_stats"]},
                {"packet_type": "environment_metrics", "count": stat["environment_metrics"]},
            ],
        }
        intervals.append(interval_data)

    response_data = {"start_date": start_date, "end_date": end_date, "intervals": intervals}

    # Validate and serialize response
    serializer = NodeStatsSerializer(data=response_data)
    if not serializer.is_valid():
        return Response(
            {"status": "error", "message": "Invalid response data"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response(serializer.validated_data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def global_packet_stats(request):
    """
    Get global packet statistics across all nodes.

    Args:
        request: The HTTP request

    Returns:
        Response containing global packet statistics grouped by time intervals
    """
    try:
        start_date, end_date, interval, interval_type = parse_stats_params(request)
    except ValueError as e:
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Build base query
    packets = RawPacket.objects.all()

    # Apply date filters if provided
    if start_date:
        packets = packets.filter(first_reported_time__gte=start_date)
    if end_date:
        packets = packets.filter(first_reported_time__lt=end_date)

    # Get total packet count for summary
    total_packets = packets.count()

    # Get interval stats
    stats = (
        packets.annotate(
            interval_start=Trunc(
                "first_reported_time", interval_type, **get_interval_trunc_kwargs(interval_type, interval)
            )
        )
        .values("interval_start")
        .annotate(packets=Count("id"))
        .order_by("interval_start")
    )

    # Format response
    intervals = []
    for stat in stats:
        interval_data = {
            "start_date": stat["interval_start"],
            "end_date": stat["interval_start"] + get_interval_delta(interval_type, interval),
            "packets": stat["packets"],
        }
        intervals.append(interval_data)

    response_data = {
        "start_date": start_date,
        "end_date": end_date,
        "intervals": intervals,
        "summary": {
            "total_packets": total_packets,
            "time_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
        },
    }

    # Validate and serialize response
    serializer = GlobalStatsSerializer(data=response_data)
    if not serializer.is_valid():
        return Response(
            {"status": "error", "message": "Invalid response data"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response(serializer.validated_data)
