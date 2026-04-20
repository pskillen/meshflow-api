"""Views for traceroute list, detail, and trigger."""

from collections import Counter
from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from nodes.models import ManagedNode, NodeOwnerClaim, ObservedNode

from .models import AutoTraceRoute
from .permission_helpers import get_triggerable_nodes_queryset, user_can_trigger_from_node
from .permissions import CanTriggerTraceroute
from .serializers import (
    AutoTraceRouteSerializer,
    TracerouteListSerializer,
    TriggerableNodeSerializer,
    TriggerTracerouteSerializer,
)
from .source_eligibility import is_managed_node_eligible_traceroute_source
from .target_selection import pick_traceroute_target
from .trigger_intervals import MANUAL_TRIGGER_MIN_INTERVAL_SEC


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

    source_node = ManagedNode.objects.filter(node_id=managed_node_id).order_by("internal_id").first()
    if source_node is None:
        return Response(
            {"managed_node_id": ["ManagedNode with this node_id not found."]},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not source_node.allow_auto_traceroute:
        return Response(
            {"detail": "This managed node does not allow traceroutes (allow_auto_traceroute is disabled)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not is_managed_node_eligible_traceroute_source(source_node):
        return Response(
            {
                "detail": (
                    "This managed node has no recent packet ingestion from the monitor bot "
                    "(within SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS). "
                    "It cannot be used as a traceroute source until the bot reports packets again."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Rate limit: firmware enforces ~30s between traceroutes per node
    last_tr = (
        AutoTraceRoute.objects.filter(source_node=source_node).order_by("-triggered_at").values("triggered_at").first()
    )
    if last_tr:
        cutoff = timezone.now() - timedelta(seconds=MANUAL_TRIGGER_MIN_INTERVAL_SEC)
        if last_tr["triggered_at"] > cutoff:
            next_allowed = last_tr["triggered_at"] + timedelta(seconds=MANUAL_TRIGGER_MIN_INTERVAL_SEC)
            remaining = max(0, (next_allowed - timezone.now()).total_seconds())
            return Response(
                {
                    "detail": f"Traceroute rate limited. "
                    f"This node's last traceroute was less than {MANUAL_TRIGGER_MIN_INTERVAL_SEC}s ago. "
                    f"Try again in {int(remaining)}s."
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

    if not user_can_trigger_from_node(request.user, source_node):
        return Response(
            {"detail": "You do not have permission to trigger traceroutes from this node."},
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

    edge_metric = request.query_params.get("edge_metric", "packets")
    if edge_metric not in ("packets", "snr"):
        edge_metric = "packets"

    try:
        data = run_heatmap_query(
            triggered_at_after=triggered_at_after,
            bbox=bbox,
            constellation_id=constellation_id,
            edge_metric=edge_metric,
        )
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception("heatmap_edges: Neo4j query failed: %s", e)
        return Response(
            {"detail": "Failed to fetch heatmap data."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(data)


def _parse_window(request):
    """Parse ``triggered_at_after`` / ``triggered_at_before`` from query params."""
    from django.utils.dateparse import parse_datetime

    triggered_at_after = None
    if request.query_params.get("triggered_at_after"):
        dt = parse_datetime(request.query_params["triggered_at_after"])
        if dt:
            triggered_at_after = dt

    triggered_at_before = None
    if request.query_params.get("triggered_at_before"):
        dt = parse_datetime(request.query_params["triggered_at_before"])
        if dt:
            triggered_at_before = dt

    return triggered_at_after, triggered_at_before


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def feeder_reach(request):
    """Per-target attempt and success counts for one feeder.

    Returns one row per ObservedNode that the requested ManagedNode has
    attempted a traceroute to in the window, with attempt and success counts.
    The frontend uses this single payload to render dots, client-side H3
    hexagons, and a concave-hull polygon. See
    ``docs/features/traceroute/coverage.md``.
    """
    from .reach import compute_reach

    feeder_param = request.query_params.get("feeder_id")
    if not feeder_param:
        return Response(
            {"detail": "feeder_id query param is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        feeder_id = int(feeder_param)
    except ValueError:
        return Response(
            {"detail": "feeder_id must be an integer."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    feeder = ManagedNode.objects.filter(node_id=feeder_id).first()
    if feeder is None:
        return Response({"detail": "Feeder not found."}, status=status.HTTP_404_NOT_FOUND)

    triggered_at_after, triggered_at_before = _parse_window(request)

    rows = compute_reach(
        triggered_at_after=triggered_at_after,
        triggered_at_before=triggered_at_before,
        feeder_id=feeder_id,
    )

    if rows:
        feeder_meta = {
            "managed_node_id": rows[0].feeder_managed_node_id,
            "node_id": rows[0].feeder_node_id,
            "node_id_str": rows[0].feeder_node_id_str,
            "short_name": rows[0].feeder_short_name,
            "long_name": rows[0].feeder_long_name,
            "lat": rows[0].feeder_lat,
            "lng": rows[0].feeder_lng,
        }
    else:
        from common.mesh_node_helpers import meshtastic_id_to_hex

        observed = ObservedNode.objects.filter(node_id=feeder.node_id).first()
        feeder_meta = {
            "managed_node_id": str(feeder.internal_id),
            "node_id": feeder.node_id,
            "node_id_str": meshtastic_id_to_hex(feeder.node_id),
            "short_name": (observed.short_name if observed else None) or feeder.name,
            "long_name": observed.long_name if observed else None,
            "lat": feeder.default_location_latitude,
            "lng": feeder.default_location_longitude,
        }

    targets = [
        {
            "node_id": r.target_node_id,
            "node_id_str": r.target_node_id_str,
            "short_name": r.target_short_name,
            "long_name": r.target_long_name,
            "lat": r.target_lat,
            "lng": r.target_lng,
            "attempts": r.attempts,
            "successes": r.successes,
        }
        for r in rows
    ]

    return Response(
        {
            "feeder": feeder_meta,
            "targets": targets,
            "meta": {
                "window": {
                    "start": triggered_at_after.isoformat() if triggered_at_after else None,
                    "end": triggered_at_before.isoformat() if triggered_at_before else None,
                },
            },
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def constellation_coverage(request):
    """Server-side H3-binned reach for an entire constellation.

    Aggregates every (feeder, target) pair where the feeder is a ManagedNode
    in the requested constellation, then bins the targets by H3 cell at the
    requested resolution (default 6, ~3km edge). Each hex returns total
    attempts/successes and the count of contributing feeders/targets.
    """
    import h3

    from .reach import compute_reach

    constellation_param = request.query_params.get("constellation_id")
    if not constellation_param:
        return Response(
            {"detail": "constellation_id query param is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        constellation_id = int(constellation_param)
    except ValueError:
        return Response(
            {"detail": "constellation_id must be an integer."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    h3_resolution = 6
    if request.query_params.get("h3_resolution"):
        try:
            h3_resolution = int(request.query_params["h3_resolution"])
        except ValueError:
            pass
    h3_resolution = max(0, min(15, h3_resolution))

    triggered_at_after, triggered_at_before = _parse_window(request)

    rows = compute_reach(
        triggered_at_after=triggered_at_after,
        triggered_at_before=triggered_at_before,
        constellation_id=constellation_id,
    )

    bins: dict = {}
    for r in rows:
        cell = h3.latlng_to_cell(r.target_lat, r.target_lng, h3_resolution)
        existing = bins.get(cell)
        if existing is None:
            bins[cell] = {
                "attempts": r.attempts,
                "successes": r.successes,
                "feeders": {r.feeder_node_id},
                "targets": {r.target_node_id},
            }
        else:
            existing["attempts"] += r.attempts
            existing["successes"] += r.successes
            existing["feeders"].add(r.feeder_node_id)
            existing["targets"].add(r.target_node_id)

    hexes = []
    for cell, agg in bins.items():
        centre_lat, centre_lng = h3.cell_to_latlng(cell)
        hexes.append(
            {
                "h3_index": cell,
                "centre_lat": centre_lat,
                "centre_lng": centre_lng,
                "attempts": agg["attempts"],
                "successes": agg["successes"],
                "contributing_feeders": len(agg["feeders"]),
                "contributing_targets": len(agg["targets"]),
            }
        )
    hexes.sort(key=lambda h: h["h3_index"])

    return Response(
        {
            "constellation_id": constellation_id,
            "h3_resolution": h3_resolution,
            "hexes": hexes,
            "meta": {
                "window": {
                    "start": triggered_at_after.isoformat() if triggered_at_after else None,
                    "end": triggered_at_before.isoformat() if triggered_at_before else None,
                },
            },
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def traceroute_stats(request):
    """Traceroute statistics: sources, success/failure, top routers, by source, success over time."""
    from django.utils.dateparse import parse_datetime

    from common.mesh_node_helpers import meshtastic_id_to_hex

    triggered_after = None
    if request.query_params.get("triggered_at_after"):
        dt = parse_datetime(request.query_params["triggered_at_after"])
        if dt:
            triggered_after = dt

    qs = AutoTraceRoute.objects.all()
    if triggered_after:
        qs = qs.filter(triggered_at__gte=triggered_after)

    # Sources: by trigger_type
    sources = list(qs.values("trigger_type").annotate(count=Count("id")).order_by("-count"))

    # Success/failure: completed vs failed only
    success_failure = list(
        qs.filter(status__in=[AutoTraceRoute.STATUS_COMPLETED, AutoTraceRoute.STATUS_FAILED])
        .values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # Top routers: intermediate nodes from completed traceroutes
    UNKNOWN_NODE_ID = 0xFFFFFFFF
    router_counts = Counter()
    completed_qs = qs.filter(status=AutoTraceRoute.STATUS_COMPLETED).select_related("source_node", "target_node")
    for tr in completed_qs:
        src_id = tr.source_node.node_id if tr.source_node else None
        tgt_id = tr.target_node.node_id if tr.target_node else None
        exclude_ids = {src_id, tgt_id, UNKNOWN_NODE_ID}
        for item in (tr.route or []) + (tr.route_back or []):
            nid = item.get("node_id")
            if nid is not None and nid not in exclude_ids:
                router_counts[nid] += 1

    top_router_node_ids = [nid for nid, _ in router_counts.most_common(15)]
    observed_by_id = {}
    if top_router_node_ids:
        for o in ObservedNode.objects.filter(node_id__in=top_router_node_ids).values("node_id", "short_name"):
            observed_by_id[o["node_id"]] = o

    top_routers = [
        {
            "node_id": nid,
            "node_id_str": meshtastic_id_to_hex(nid),
            "short_name": observed_by_id.get(nid, {}).get("short_name") or meshtastic_id_to_hex(nid),
            "count": router_counts[nid],
        }
        for nid in top_router_node_ids
    ]

    # Per source managed node (same triggered_at window as qs)
    by_source_rows = list(
        qs.values("source_node_id").annotate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=AutoTraceRoute.STATUS_COMPLETED)),
            failed=Count("id", filter=Q(status=AutoTraceRoute.STATUS_FAILED)),
        )
    )
    source_internal_ids = [r["source_node_id"] for r in by_source_rows]
    managed_by_internal_id = {m.internal_id: m for m in ManagedNode.objects.filter(internal_id__in=source_internal_ids)}
    mesh_node_ids = [m.node_id for m in managed_by_internal_id.values()]
    observed_short_by_mesh_id = {}
    if mesh_node_ids:
        for o in ObservedNode.objects.filter(node_id__in=mesh_node_ids).values("node_id", "short_name"):
            observed_short_by_mesh_id[o["node_id"]] = o["short_name"]

    by_source = []
    for row in by_source_rows:
        mn = managed_by_internal_id.get(row["source_node_id"])
        if mn is None:
            continue
        completed_n = row["completed"]
        failed_n = row["failed"]
        finished = completed_n + failed_n
        success_rate = None if finished == 0 else completed_n / finished
        short_name = observed_short_by_mesh_id.get(mn.node_id) or mn.name
        by_source.append(
            {
                "managed_node_id": str(mn.internal_id),
                "node_id": mn.node_id,
                "node_id_str": meshtastic_id_to_hex(mn.node_id),
                "name": mn.name,
                "short_name": short_name,
                "total": row["total"],
                "completed": completed_n,
                "failed": failed_n,
                "success_rate": success_rate,
            }
        )
    by_source.sort(key=lambda x: (-x["total"], x["node_id_str"]))

    # Per target observed node (same triggered_at window as qs)
    by_target_rows = list(
        qs.values("target_node_id").annotate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=AutoTraceRoute.STATUS_COMPLETED)),
            failed=Count("id", filter=Q(status=AutoTraceRoute.STATUS_FAILED)),
        )
    )
    target_internal_ids = [r["target_node_id"] for r in by_target_rows]
    observed_by_internal_id = {
        o.internal_id: o for o in ObservedNode.objects.filter(internal_id__in=target_internal_ids)
    }

    by_target = []
    for row in by_target_rows:
        on = observed_by_internal_id.get(row["target_node_id"])
        if on is None:
            continue
        completed_n = row["completed"]
        failed_n = row["failed"]
        finished = completed_n + failed_n
        success_rate = None if finished == 0 else completed_n / finished
        by_target.append(
            {
                "node_id": on.node_id,
                "node_id_str": meshtastic_id_to_hex(on.node_id),
                "short_name": on.short_name,
                "long_name": on.long_name,
                "total": row["total"],
                "completed": completed_n,
                "failed": failed_n,
                "success_rate": success_rate,
            }
        )
    by_target.sort(key=lambda x: (-x["total"], x["node_id_str"]))

    # Success over time: last 14 days, from StatsSnapshot or on-demand
    fourteen_days_ago = timezone.now() - timedelta(days=14)
    success_over_time = _get_success_over_time(fourteen_days_ago)

    return Response(
        {
            "sources": sources,
            "success_failure": success_failure,
            "top_routers": top_routers,
            "by_source": by_source,
            "by_target": by_target,
            "success_over_time": success_over_time,
        }
    )


def _get_success_over_time(since):
    """Return [{date, completed, failed}, ...] for last 14 days from StatsSnapshot + gaps."""
    from datetime import date
    from datetime import datetime as dt_class

    from stats.models import StatsSnapshot

    # Build date range (oldest first for ordering)
    today = timezone.now().date()
    dates_needed = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]

    # Fetch from StatsSnapshot
    snapshots = StatsSnapshot.objects.filter(
        stat_type="tr_success_daily",
        constellation__isnull=True,
        recorded_at__gte=since,
    ).order_by("recorded_at")

    result_by_date = {}
    for s in snapshots:
        val = s.value or {}
        dt = val.get("date")
        if dt:
            result_by_date[dt] = {
                "date": dt,
                "completed": val.get("completed", 0),
                "failed": val.get("failed", 0),
            }

    # Fill gaps with on-demand aggregation from AutoTraceRoute
    gaps = [d for d in dates_needed if d not in result_by_date]
    if gaps:
        since_dt = timezone.make_aware(dt_class.combine(date.fromisoformat(gaps[0]), dt_class.min.time()))
        qs = (
            AutoTraceRoute.objects.filter(
                triggered_at__gte=since_dt,
                status__in=[AutoTraceRoute.STATUS_COMPLETED, AutoTraceRoute.STATUS_FAILED],
            )
            .annotate(date=TruncDate("triggered_at"))
            .values("date", "status")
            .annotate(count=Count("id"))
        )
        for row in qs:
            dt_str = row["date"].isoformat() if row["date"] else None
            if dt_str and dt_str in gaps:
                if dt_str not in result_by_date:
                    result_by_date[dt_str] = {"date": dt_str, "completed": 0, "failed": 0}
                result_by_date[dt_str][row["status"]] = row["count"]

    # Build ordered result (oldest first for line chart)
    return [result_by_date.get(d, {"date": d, "completed": 0, "failed": 0}) for d in dates_needed]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def traceroute_triggerable_nodes(request):
    """Returns ManagedNodes the current user can trigger traceroutes from."""
    qs = get_triggerable_nodes_queryset(request.user)
    serializer = TriggerableNodeSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def traceroute_can_trigger(request):
    """Returns whether the current user can trigger traceroutes (has at least one triggerable node)."""
    can = get_triggerable_nodes_queryset(request.user).exists()
    return Response({"can_trigger": can})
