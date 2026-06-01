"""Read APIs for MeshCore passive packet path evidence."""

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from meshcore_packet_path.models import MeshCorePathEdgeBucket, MeshCorePathSegmentResolution, SegmentStatus
from meshcore_packet_path.serializers import (
    MeshCorePathEdgeBucketSerializer,
    MeshCorePathSegmentAnnotateSerializer,
    MeshCorePathSegmentSerializer,
)


def _parse_dt_param(value: str | None):
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


class PathTracingEdgesListView(generics.ListAPIView):
    """GET /api/meshcore/path-tracing/edges/ — bucketed hash-chain edges."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MeshCorePathEdgeBucketSerializer

    def get_queryset(self):
        qs = MeshCorePathEdgeBucket.objects.select_related(
            "observer",
            "constellation",
            "from_node",
            "to_node",
        ).order_by("-bucket_start", "-observation_count")

        params = self.request.query_params
        after = _parse_dt_param(params.get("bucket_start_after"))
        before = _parse_dt_param(params.get("bucket_start_before"))
        if after:
            qs = qs.filter(bucket_start__gte=after)
        if before:
            qs = qs.filter(bucket_start__lt=before)

        observer = params.get("observer")
        if observer:
            qs = qs.filter(observer__internal_id=observer)

        constellation = params.get("constellation")
        if constellation:
            qs = qs.filter(constellation_id=constellation)

        from_hash = params.get("from_hash")
        if from_hash:
            qs = qs.filter(from_hash=from_hash.lower())

        to_hash = params.get("to_hash")
        if to_hash:
            qs = qs.filter(to_hash=to_hash.lower())

        resolved = params.get("resolved")
        if resolved is not None:
            if resolved.lower() in ("true", "1", "yes"):
                qs = qs.filter(from_node__isnull=False, to_node__isnull=False)
            elif resolved.lower() in ("false", "0", "no"):
                qs = qs.filter(Q(from_node__isnull=True) | Q(to_node__isnull=True))

        return qs


class PathTracingSegmentListView(generics.ListAPIView):
    """GET /api/meshcore/path-tracing/segments/ — segment resolution table."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MeshCorePathSegmentSerializer

    def get_queryset(self):
        qs = MeshCorePathSegmentResolution.objects.select_related("observed_node").order_by("-last_seen_at")
        params = self.request.query_params

        status_val = params.get("status")
        if status_val:
            qs = qs.filter(status=status_val)

        hash_mode = params.get("hash_mode")
        if hash_mode is not None and hash_mode != "":
            qs = qs.filter(hash_mode=int(hash_mode))

        hash_size = params.get("hash_size")
        if hash_size is not None and hash_size != "":
            qs = qs.filter(hash_size=int(hash_size))

        segment_hash = params.get("segment_hash")
        if segment_hash:
            qs = qs.filter(segment_hash=segment_hash.lower())

        resolved = params.get("resolved")
        if resolved is not None:
            if resolved.lower() in ("true", "1", "yes"):
                qs = qs.filter(status=SegmentStatus.RESOLVED)
            elif resolved.lower() in ("false", "0", "no"):
                qs = qs.exclude(status=SegmentStatus.RESOLVED)

        return qs


class PathTracingSegmentDetailView(APIView):
    """GET/PATCH /api/meshcore/path-tracing/segments/<uuid>/"""

    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        return MeshCorePathSegmentResolution.objects.select_related("observed_node").get(pk=pk)

    def get(self, request, pk):
        segment = self.get_object(pk)
        return Response(MeshCorePathSegmentSerializer(segment).data)

    def patch(self, request, pk):
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)

        segment = self.get_object(pk)
        ser = MeshCorePathSegmentAnnotateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)

        node = ser.resolve_observed_node()
        if ser.validated_data.get("observed_node_id") or ser.validated_data.get("node_id_str"):
            if node is None and (
                ser.validated_data.get("observed_node_id") or (ser.validated_data.get("node_id_str") or "").strip()
            ):
                return Response(
                    {"detail": "Observed node not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if "observed_node_id" in ser.validated_data or ser.validated_data.get("node_id_str") is not None:
            segment.observed_node = node
            if node is not None:
                segment.status = SegmentStatus.RESOLVED
            elif ser.validated_data.get("observed_node_id") is None and (ser.validated_data.get("node_id_str") == ""):
                segment.status = SegmentStatus.UNKNOWN

        if "status" in ser.validated_data:
            segment.status = ser.validated_data["status"]

        segment.source = "manual_admin"
        segment.resolver_version = segment.resolver_version + 1
        segment.save()

        return Response(MeshCorePathSegmentSerializer(segment).data)
