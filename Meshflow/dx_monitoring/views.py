"""Read-only DX event API and staff node exclusion for DX detection."""

from django.db.models import Count, IntegerField, OuterRef, Prefetch, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework import permissions, status, views, viewsets
from rest_framework.response import Response

from dx_monitoring.models import DxEvent, DxEventObservation, DxEventState, DxEventTraceroute, DxNodeMetadata
from dx_monitoring.serializers import (
    DxEventDetailSerializer,
    DxEventListSerializer,
    DxNodeExclusionRequestSerializer,
    DxNodeExclusionResponseSerializer,
)
from nodes.models import ObservedNode


def _parse_dt(raw: str):
    dt = parse_datetime(raw)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


_exploration_attempt_count_sq = (
    DxEventTraceroute.objects.filter(event_id=OuterRef("pk"))
    .values("event_id")
    .annotate(_c=Count("id"))
    .values("_c")[:1]
)


class DxEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Staff-only read API for DX detection events.

    List: GET /api/dx/events/
    Detail: GET /api/dx/events/{uuid}/
    """

    permission_classes = [permissions.IsAdminUser]
    lookup_field = "pk"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return DxEventDetailSerializer
        return DxEventListSerializer

    def get_queryset(self):
        qs = (
            DxEvent.objects.all()
            .select_related("constellation", "destination", "destination__dx_metadata", "last_observer")
            .annotate(
                evidence_count=Count("observations", distinct=True),
                exploration_attempt_count=Coalesce(
                    Subquery(_exploration_attempt_count_sq, output_field=IntegerField()),
                    Value(0),
                ),
            )
            .order_by("-last_observed_at")
        )
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                Prefetch(
                    "observations",
                    queryset=DxEventObservation.objects.select_related(
                        "raw_packet",
                        "packet_observation",
                        "observer",
                    ).order_by("-observed_at"),
                ),
                Prefetch(
                    "traceroute_explorations",
                    queryset=DxEventTraceroute.objects.select_related(
                        "source_node",
                        "event__destination",
                        "auto_traceroute",
                        "auto_traceroute__target_node",
                    ).order_by("-created_at"),
                ),
            )
        params = self.request.query_params

        if state := params.get("state"):
            qs = qs.filter(state=state)
        if reason := params.get("reason_code"):
            qs = qs.filter(reason_code=reason)
        if cid := params.get("constellation"):
            try:
                qs = qs.filter(constellation_id=int(cid))
            except ValueError:
                qs = qs.none()
        if raw := params.get("destination_node_id"):
            try:
                qs = qs.filter(destination__node_id=int(raw))
            except ValueError:
                qs = qs.none()
        if raw := params.get("last_observer_id"):
            qs = qs.filter(last_observer_id=raw)

        if params.get("active_now") in ("1", "true", "True", "yes"):
            now = timezone.now()
            qs = qs.filter(state=DxEventState.ACTIVE, active_until__gte=now)

        if raw := params.get("last_observed_after"):
            dt = _parse_dt(raw)
            if dt:
                qs = qs.filter(last_observed_at__gte=dt)
        if raw := params.get("last_observed_before"):
            dt = _parse_dt(raw)
            if dt:
                qs = qs.filter(last_observed_at__lte=dt)
        if raw := params.get("first_observed_after"):
            dt = _parse_dt(raw)
            if dt:
                qs = qs.filter(first_observed_at__gte=dt)
        if raw := params.get("first_observed_before"):
            dt = _parse_dt(raw)
            if dt:
                qs = qs.filter(first_observed_at__lte=dt)

        if params.get("recent_only") in ("1", "true", "True", "yes"):
            raw_days = params.get("recent_days", "7")
            try:
                days = max(1, min(int(raw_days), 90))
            except ValueError:
                days = 7
            cutoff = timezone.now() - timezone.timedelta(days=days)
            qs = qs.filter(last_observed_at__gte=cutoff)

        return qs


class DxNodeExclusionView(views.APIView):
    """
    Create or update DxNodeMetadata for an observed node (by Meshtastic node_id).

    POST /api/dx/nodes/exclusion/
    Staff only.
    """

    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        ser = DxNodeExclusionRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        node_id = ser.validated_data["node_id"]
        exclude = ser.validated_data["exclude_from_detection"]
        notes = ser.validated_data.get("exclude_notes") or ""

        observed = ObservedNode.objects.filter(node_id=node_id).order_by("-last_heard", "-created_at").first()
        if observed is None:
            return Response(
                {"detail": "No observed node found for this node_id."},
                status=status.HTTP_404_NOT_FOUND,
            )

        meta, _ = DxNodeMetadata.objects.get_or_create(observed_node=observed)
        meta.exclude_from_detection = exclude
        meta.exclude_notes = notes
        meta.save()

        out = DxNodeExclusionResponseSerializer(
            {
                "node_id": observed.node_id,
                "node_id_str": observed.node_id_str,
                "exclude_from_detection": meta.exclude_from_detection,
                "exclude_notes": meta.exclude_notes,
                "updated_at": meta.updated_at,
            }
        )
        return Response(out.data, status=status.HTTP_200_OK)


def _resolve_observed_by_node_id(node_id: int) -> ObservedNode | None:
    return ObservedNode.objects.filter(node_id=node_id).order_by("-last_heard", "-created_at").first()


class DxNodeExclusionByNodeIdView(views.APIView):
    """
    GET current exclusion flags for an observed node by Meshtastic node_id.

    GET /api/dx/nodes/by-node-id/{node_id}/exclusion/
    Staff only.
    """

    permission_classes = [permissions.IsAdminUser]

    def get(self, request, node_id: int):
        observed = _resolve_observed_by_node_id(node_id)
        if observed is None:
            return Response(
                {"detail": "No observed node found for this node_id."},
                status=status.HTTP_404_NOT_FOUND,
            )
        meta = DxNodeMetadata.objects.filter(observed_node=observed).first()
        if meta is None:
            payload = {
                "node_id": observed.node_id,
                "node_id_str": observed.node_id_str,
                "exclude_from_detection": False,
                "exclude_notes": "",
                "updated_at": None,
            }
        else:
            payload = {
                "node_id": observed.node_id,
                "node_id_str": observed.node_id_str,
                "exclude_from_detection": meta.exclude_from_detection,
                "exclude_notes": meta.exclude_notes,
                "updated_at": meta.updated_at,
            }
        return Response(DxNodeExclusionResponseSerializer(payload).data)
