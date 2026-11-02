"""Read-only M2M data endpoints. Serializers stay in this module, not the UI ones."""

import hashlib
import json
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from django.utils import timezone

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.protocol import Protocol
from constellations.models import Constellation
from nodes.constants import INFRASTRUCTURE_ROLES
from nodes.models import ManagedNode, ManagedNodeStatus, ObservedNode, RoleSource
from stats.models import StatsSnapshot

from .authentication import M2MApiKeyAuthentication
from .throttling import M2M_THROTTLE_CLASSES
from .usage import record_m2m_request

MC_TYPE_NAMES = {0: "none", 1: "chat", 2: "repeater", 3: "room", 4: "sensor"}
MC_INFRA = (2, 3)
HEARD_WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
DEPRECATED_ROLES = {RoleSource.ROUTER_CLIENT, RoleSource.REPEATER}


class M2MView(APIView):
    authentication_classes = [M2MApiKeyAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = M2M_THROTTLE_CLASSES

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if getattr(request, "m2m_terms_action_required", False):
            response["X-M2M-Terms-Action-Required"] = "true"
        if response.status_code < 400 and request.auth is not None:
            record_m2m_request(request.auth, request.path)
        return response


def _constellation(request):
    raw = request.query_params.get("constellation")
    if not raw:
        return None
    return Constellation.objects.filter(pk=raw).first()


def _day_start(now):
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _snapshot_sum(stat_type, start, end, constellation):
    qs = StatsSnapshot.objects.filter(stat_type=stat_type, recorded_at__gte=start, recorded_at__lt=end)
    if constellation is None:
        qs = qs.filter(constellation__isnull=True)
    else:
        qs = qs.filter(constellation=constellation)
    total = 0
    latest = None
    for row in qs.order_by("recorded_at"):
        if row.recorded_at + timedelta(hours=1) > end and end != start:
            # exclude the in-progress hour when end is "now"
            if row.recorded_at + timedelta(hours=1) > timezone.now():
                continue
        value = row.value or {}
        total += int(value.get("count") or 0)
        latest = row.recorded_at
    as_of = (latest + timedelta(hours=1)) if latest else start
    return total, as_of


def _completed_range(start, end):
    """Drop the hour that has not finished yet."""
    now = timezone.now()
    hour_floor = now.replace(minute=0, second=0, microsecond=0)
    if end > hour_floor:
        end = hour_floor
    return start, end


def _nodes_heard(protocol, constellation_ignored):
    now = timezone.now()
    base = ObservedNode.objects.filter(protocol=protocol)
    windows = {
        "2h": now - timedelta(hours=2),
        "24h": now - timedelta(hours=24),
        "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30),
    }
    return {name: base.filter(last_heard__gte=threshold).count() for name, threshold in windows.items()}


def _feeders(protocol, constellation):
    qs = ManagedNode.objects.filter(protocol=protocol, deleted_at__isnull=True)
    if constellation is not None:
        qs = qs.filter(constellation=constellation)
    total = qs.count()
    active = ManagedNodeStatus.objects.filter(node__in=qs, is_sending_data=True).count()
    return {"active": active, "total": total}


def _attribution():
    return {
        "text": "Data: Meshflow",
        "url": (settings.FRONTEND_URL or "").rstrip("/"),
        "licence": "CC BY-NC 4.0",
    }


def _meshflow_url(node_id_str):
    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    if not base:
        return ""
    return f"{base}/nodes/{node_id_str}"


class MetaView(M2MView):
    def get(self, request):
        return Response(
            {
                "terms_version": settings.M2M_TERMS_VERSION,
                "licence": "CC BY-NC 4.0",
                "attribution": _attribution(),
                "rate_limits": {
                    "per_key": {
                        "minute": settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["m2m_key_min"],
                        "day": settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["m2m_key_day"],
                    }
                },
                "time": {"timezone": "UTC", "today": "00:00 UTC to now; packets.today sums completed hours only"},
            }
        )


class ConstellationsView(M2MView):
    def get(self, request):
        rows = Constellation.objects.order_by("id").values("id", "name")
        return Response(list(rows))


def _role_mix(protocol, since):
    qs = ObservedNode.objects.filter(protocol=protocol, last_heard__gte=since)
    if protocol == Protocol.MESHTASTIC:
        counts = qs.values("meshtastic_role").annotate(n=Count("internal_id"))
        out = {}
        for row in counts:
            role = row["meshtastic_role"]
            label = RoleSource(role).label if role is not None else "unknown"
            out[label] = row["n"]
        return out
    counts = qs.values("meshcore_adv_type").annotate(n=Count("internal_id"))
    out = {}
    for row in counts:
        label = MC_TYPE_NAMES.get(row["meshcore_adv_type"], "unknown")
        out[label] = out.get(label, 0) + row["n"]
    return out


class SummaryView(M2MView):
    protocol = Protocol.MESHTASTIC
    packet_stat = "packet_volume"
    cache_seconds = 60

    def get(self, request):
        query = request.META.get("QUERY_STRING", "")
        cache_key = "m2m:resp:%s:%s" % (request.path, query)
        cached = cache.get(cache_key)
        if cached is not None:
            response = Response(cached)
            response["Cache-Control"] = f"max-age={self.cache_seconds}"
            return response
        constellation = _constellation(request)
        now = timezone.now()
        day_start = _day_start(now)
        start, end = _completed_range(day_start, now)
        today, as_of = _snapshot_sum(self.packet_stat, start, end, constellation)
        last_start, last_end = _completed_range(now - timedelta(hours=24), now)
        last_24h, _ = _snapshot_sum(self.packet_stat, last_start, last_end, constellation)
        since_24h = now - timedelta(hours=24)
        role_key = "nodes_by_role_24h" if self.protocol == Protocol.MESHTASTIC else "nodes_by_type_24h"
        mix = _role_mix(self.protocol, since_24h)
        if self.protocol == Protocol.MESHTASTIC:
            infra_count = ObservedNode.objects.filter(
                protocol=self.protocol,
                last_heard__gte=since_24h,
                meshtastic_role__in=INFRASTRUCTURE_ROLES,
            ).count()
        else:
            infra_count = ObservedNode.objects.filter(
                protocol=self.protocol,
                last_heard__gte=since_24h,
                meshcore_adv_type__in=MC_INFRA,
            ).count()
        body = {
            "protocol": "meshtastic" if self.protocol == Protocol.MESHTASTIC else "meshcore",
            "constellation": None if constellation is None else constellation.id,
            "generated_at": now.isoformat().replace("+00:00", "Z"),
            "packets": {
                "today": today,
                "day_start": day_start.isoformat().replace("+00:00", "Z"),
                "as_of": as_of.isoformat().replace("+00:00", "Z"),
                "last_24h": last_24h,
            },
            "nodes_heard": _nodes_heard(self.protocol, constellation),
            role_key: mix,
            "infra_nodes_24h": infra_count,
            "feeders": _feeders(self.protocol, constellation),
            "attribution": _attribution(),
        }
        cache.set(cache_key, body, self.cache_seconds)
        response = Response(body)
        response["Cache-Control"] = f"max-age={self.cache_seconds}"
        response["ETag"] = hashlib.sha256(json.dumps(body, default=str, sort_keys=True).encode()).hexdigest()[:16]
        return response


class MeshCoreSummaryView(SummaryView):
    protocol = Protocol.MESHCORE
    packet_stat = "mc_packet_volume"


_METRIC_TYPES = {
    ("meshtastic", "online_nodes"): "online_nodes",
    ("meshtastic", "packet_volume"): "packet_volume",
    ("meshtastic", "new_nodes"): "new_nodes",
    ("meshcore", "online_nodes"): "mc_online_nodes",
    ("meshcore", "packet_volume"): "mc_packet_volume",
    ("meshcore", "new_nodes"): "mc_new_nodes",
}


class TimeseriesView(M2MView):
    protocol_name = "meshtastic"
    cache_seconds = 300

    def get(self, request):
        metric = request.query_params.get("metric") or ""
        interval = request.query_params.get("interval") or "hour"
        stat_type = _METRIC_TYPES.get((self.protocol_name, metric))
        if stat_type is None or interval not in ("hour", "day"):
            return Response({"detail": "metric and interval are required."}, status=400)
        now = timezone.now()
        raw_from = request.query_params.get("from")
        raw_to = request.query_params.get("to")
        end = _parse_dt(raw_to) or now
        default_span = timedelta(days=7)
        start = _parse_dt(raw_from) or (end - default_span)
        max_span = timedelta(days=31 if interval == "hour" else 400)
        if end - start > max_span:
            return Response({"detail": "Requested range exceeds the cap."}, status=400)
        query = request.META.get("QUERY_STRING", "")
        cache_key = "m2m:resp:%s:%s" % (request.path, query)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        constellation = _constellation(request)
        qs = StatsSnapshot.objects.filter(stat_type=stat_type, recorded_at__gte=start, recorded_at__lt=end)
        if constellation is None:
            qs = qs.filter(constellation__isnull=True)
        else:
            qs = qs.filter(constellation=constellation)
        if interval == "hour":
            points = [
                {"t": row.recorded_at.isoformat().replace("+00:00", "Z"), "v": int((row.value or {}).get("count") or 0)}
                for row in qs.order_by("recorded_at")
            ]
        else:
            buckets = {}
            for row in qs.order_by("recorded_at"):
                day = row.recorded_at.date().isoformat()
                buckets[day] = buckets.get(day, 0) + int((row.value or {}).get("count") or 0)
            points = [{"t": f"{day}T00:00:00Z", "v": value} for day, value in buckets.items()]
        body = {"metric": metric, "interval": interval, "unit": "count", "points": points}
        cache.set(cache_key, body, self.cache_seconds)
        response = Response(body)
        response["Cache-Control"] = f"max-age={self.cache_seconds}"
        return response


class MeshCoreTimeseriesView(TimeseriesView):
    protocol_name = "meshcore"


def _parse_dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


class InfraNodesView(M2MView):
    protocol = Protocol.MESHTASTIC
    cache_seconds = 300

    def get(self, request):
        heard = request.query_params.get("heard_within") or "7d"
        if heard not in HEARD_WINDOWS:
            return Response({"detail": "heard_within must be 24h, 7d, or 30d."}, status=400)
        query = request.META.get("QUERY_STRING", "")
        cache_key = "m2m:resp:%s:%s" % (request.path, query)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        since = timezone.now() - HEARD_WINDOWS[heard]
        qs = ObservedNode.objects.filter(
            protocol=self.protocol, m2m_opt_out=False, last_heard__gte=since
        ).select_related("latest_status")
        if self.protocol == Protocol.MESHTASTIC:
            qs = qs.filter(meshtastic_role__in=INFRASTRUCTURE_ROLES)
        else:
            qs = qs.filter(meshcore_adv_type__in=MC_INFRA)
        qs = qs.order_by("-last_heard")
        page_size = min(int(request.query_params.get("page_size") or 100), 1000)
        page = max(int(request.query_params.get("page") or 1), 1)
        start = (page - 1) * page_size
        rows = []
        for node in qs[start : start + page_size]:
            rows.append(_infra_row(node))
        body = {"count": qs.count(), "page": page, "page_size": page_size, "results": rows}
        cache.set(cache_key, body, self.cache_seconds)
        response = Response(body)
        response["Cache-Control"] = f"max-age={self.cache_seconds}"
        return response


class MeshCoreInfraNodesView(InfraNodesView):
    protocol = Protocol.MESHCORE


def _infra_row(node):
    status = getattr(node, "latest_status", None)
    if node.protocol == Protocol.MESHTASTIC:
        role = RoleSource(node.meshtastic_role).label if node.meshtastic_role is not None else "unknown"
        health = None
        if status is not None:
            health = {
                "battery_level": status.battery_level,
                "voltage": status.voltage,
                "channel_utilization": status.meshtastic_channel_utilization,
                "air_util_tx": status.meshtastic_air_util_tx,
                "uptime_seconds": status.uptime_seconds,
                "reported_at": status.metrics_reported_time,
            }
        return {
            "id": node.node_id_str,
            "long_name": node.long_name,
            "short_name": node.short_name,
            "role": role,
            "role_deprecated": node.meshtastic_role in DEPRECATED_ROLES,
            "hw_model": node.meshtastic_hw_model,
            "last_heard": node.last_heard,
            "meshflow_url": _meshflow_url(node.node_id_str),
            "health": health,
        }
    return {
        "id": node.node_id_str,
        "long_name": node.long_name,
        "short_name": node.short_name,
        "type": MC_TYPE_NAMES.get(node.meshcore_adv_type, "unknown"),
        "last_heard": node.last_heard,
        "meshflow_url": _meshflow_url(node.node_id_str),
        "health": None,
    }
