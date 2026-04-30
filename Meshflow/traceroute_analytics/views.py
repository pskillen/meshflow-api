"""Analytics and visualization API views for traceroutes (Neo4j heatmap, reach, stats)."""

from collections import Counter
from datetime import timedelta

from django.db.models import CharField, Count, Q, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from nodes.models import ManagedNode, ObservedNode
from traceroute.models import AutoTraceRoute


def _traceroute_stats_by_strategy(qs):
    """Aggregate counts per coalesced target_strategy for a queryset."""
    legacy_label = AutoTraceRoute.TARGET_STRATEGY_LEGACY
    by_strategy_rows = (
        qs.annotate(
            strat=Coalesce(
                "target_strategy",
                Value(legacy_label, output_field=CharField(max_length=24)),
            )
        )
        .values("strat")
        .annotate(
            completed=Count("id", filter=Q(status=AutoTraceRoute.STATUS_COMPLETED)),
            failed=Count("id", filter=Q(status=AutoTraceRoute.STATUS_FAILED)),
            pending=Count("id", filter=Q(status=AutoTraceRoute.STATUS_PENDING)),
            sent=Count("id", filter=Q(status=AutoTraceRoute.STATUS_SENT)),
        )
    )
    return {
        row["strat"]: {
            "completed": row["completed"],
            "failed": row["failed"],
            "pending": row["pending"],
            "sent": row["sent"],
        }
        for row in by_strategy_rows
    }


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

    source_node_id = request.query_params.get("source_node_id")
    if source_node_id is not None and str(source_node_id).strip() != "":
        try:
            source_node_id = int(source_node_id)
        except ValueError:
            source_node_id = None
    else:
        source_node_id = None

    ts_param = request.query_params.get("target_strategy")
    target_strategy_tokens = [s.strip() for s in ts_param.split(",") if s.strip()] if ts_param else None

    try:
        data = run_heatmap_query(
            triggered_at_after=triggered_at_after,
            bbox=bbox,
            constellation_id=constellation_id,
            edge_metric=edge_metric,
            source_node_id=source_node_id,
            target_strategy_tokens=target_strategy_tokens,
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


def _parse_target_strategy_tokens(request) -> list[str] | None:
    """Comma-separated ``target_strategy`` query values, or None if absent/empty."""
    param = request.query_params.get("target_strategy")
    if not param:
        return None
    tokens = [t.strip() for t in param.split(",") if t.strip()]
    return tokens or None


def _include_targets_from_request(request) -> bool:
    val = request.query_params.get("include_targets")
    if val is None:
        return False
    return val.strip().lower() in ("1", "true", "yes", "on")


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

    feeder = ManagedNode.objects.filter(node_id=feeder_id, deleted_at__isnull=True).first()
    if feeder is None:
        return Response({"detail": "Feeder not found."}, status=status.HTTP_404_NOT_FOUND)

    triggered_at_after, triggered_at_before = _parse_window(request)
    strategy_tokens = _parse_target_strategy_tokens(request)

    rows = compute_reach(
        triggered_at_after=triggered_at_after,
        triggered_at_before=triggered_at_before,
        feeder_id=feeder_id,
        target_strategy_tokens=strategy_tokens,
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
    strategy_tokens = _parse_target_strategy_tokens(request)
    include_targets = _include_targets_from_request(request)

    from .reach import aggregate_reach_rows_to_constellation_targets, compute_reach, constellation_feeder_markers

    rows = compute_reach(
        triggered_at_after=triggered_at_after,
        triggered_at_before=triggered_at_before,
        constellation_id=constellation_id,
        target_strategy_tokens=strategy_tokens,
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

    payload: dict = {
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
    if include_targets:
        payload["targets"] = aggregate_reach_rows_to_constellation_targets(rows)
        payload["feeders"] = constellation_feeder_markers(constellation_id)

    return Response(payload)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def traceroute_stats(request):
    """Traceroute statistics: sources, success/failure, top routers, by source, success over time.

    Optional query params: triggered_at_after, source_node (managed mesh node_id, same as list).
    ``success_over_time`` is one row per calendar day from ``triggered_at_after`` (date) through
    today (default window when omitted: last 14 days), using the same ``qs`` filters as other aggregates.
    ``by_strategy`` includes all trigger types; ``by_strategy_excluding_external`` omits external
    mesh reports for success-rate style breakdowns (no hypothesis).
    """
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

    source_node = request.query_params.get("source_node")
    if source_node:
        try:
            mn = ManagedNode.objects.get(node_id=int(source_node), deleted_at__isnull=True)
            qs = qs.filter(source_node=mn)
        except ValueError, ManagedNode.DoesNotExist:
            pass

    # Sources: by trigger_type
    sources = list(qs.values("trigger_type").annotate(count=Count("id")).order_by("-count"))

    # Success/failure: completed vs failed only
    success_failure = list(
        qs.filter(status__in=[AutoTraceRoute.STATUS_COMPLETED, AutoTraceRoute.STATUS_FAILED])
        .values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    by_strategy = _traceroute_stats_by_strategy(qs)
    by_strategy_excluding_external = _traceroute_stats_by_strategy(
        qs.exclude(trigger_type=AutoTraceRoute.TRIGGER_TYPE_EXTERNAL)
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
    managed_by_internal_id = {
        m.internal_id: m
        for m in ManagedNode.objects.filter(internal_id__in=source_internal_ids, deleted_at__isnull=True)
    }
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

    # Daily completed/failed counts over the same window as ``qs`` (triggered_at_after + source_node).
    end_date = timezone.now().date()
    if triggered_after:
        start_date = timezone.localtime(triggered_after).date()
    else:
        start_date = end_date - timedelta(days=13)
    if start_date > end_date:
        start_date = end_date
    success_over_time = _success_over_time_daily(qs, start_date, end_date)

    return Response(
        {
            "sources": sources,
            "success_failure": success_failure,
            "top_routers": top_routers,
            "by_source": by_source,
            "by_target": by_target,
            "success_over_time": success_over_time,
            "by_strategy": by_strategy,
            "by_strategy_excluding_external": by_strategy_excluding_external,
        }
    )


def _success_over_time_daily(qs, start_date, end_date):
    """Return [{date, completed, failed}, ...] for each calendar day from start_date through end_date inclusive.

    Uses the same filtered ``qs`` as the rest of traceroute_stats (time window, source_node, etc.).
    """
    from datetime import datetime as dt_class

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    dates_needed = []
    d = start_date
    while d <= end_date:
        dates_needed.append(d.isoformat())
        d = d + timedelta(days=1)

    start_dt = timezone.make_aware(dt_class.combine(start_date, dt_class.min.time()))
    end_exclusive = timezone.make_aware(dt_class.combine(end_date + timedelta(days=1), dt_class.min.time()))

    agg_rows = (
        qs.filter(
            triggered_at__gte=start_dt,
            triggered_at__lt=end_exclusive,
            status__in=[AutoTraceRoute.STATUS_COMPLETED, AutoTraceRoute.STATUS_FAILED],
        )
        .annotate(day=TruncDate("triggered_at"))
        .values("day", "status")
        .annotate(count=Count("id"))
    )

    result_by_date = {dt: {"date": dt, "completed": 0, "failed": 0} for dt in dates_needed}
    for row in agg_rows:
        day = row["day"]
        if day is None:
            continue
        dt_str = day.isoformat()
        if dt_str not in result_by_date:
            continue
        st = row["status"]
        if st == AutoTraceRoute.STATUS_COMPLETED:
            result_by_date[dt_str]["completed"] += row["count"]
        elif st == AutoTraceRoute.STATUS_FAILED:
            result_by_date[dt_str]["failed"] += row["count"]

    return [result_by_date[dt] for dt in dates_needed]
