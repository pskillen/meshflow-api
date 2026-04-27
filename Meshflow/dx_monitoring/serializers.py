"""Serializers for DX monitoring visibility API."""

from collections import Counter

from rest_framework import serializers

from common.mesh_node_helpers import meshtastic_id_to_hex
from constellations.models import Constellation
from dx_monitoring.models import (
    DxEvent,
    DxEventObservation,
    DxEventTraceroute,
    DxNodeMetadata,
    DxNotificationCategory,
)
from nodes.models import ManagedNode, ObservedNode
from traceroute.models import AutoTraceRoute


class ConstellationMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Constellation
        fields = ("id", "name")


class DxManagedNodeMinimalSerializer(serializers.ModelSerializer):
    node_id_str = serializers.SerializerMethodField()

    class Meta:
        model = ManagedNode
        fields = ("internal_id", "node_id", "node_id_str", "name")

    def get_node_id_str(self, obj: ManagedNode) -> str:
        return meshtastic_id_to_hex(obj.node_id)


class DxDestinationSerializer(serializers.ModelSerializer):
    """Observed destination node with nested DX metadata (exclusion flags)."""

    dx_metadata = serializers.SerializerMethodField()

    class Meta:
        model = ObservedNode
        fields = ("internal_id", "node_id", "node_id_str", "short_name", "long_name", "dx_metadata")

    def get_dx_metadata(self, obj: ObservedNode) -> dict:
        try:
            m: DxNodeMetadata = obj.dx_metadata
        except DxNodeMetadata.DoesNotExist:
            return {
                "exclude_from_detection": False,
                "exclude_notes": "",
                "updated_at": None,
            }
        return {
            "exclude_from_detection": m.exclude_from_detection,
            "exclude_notes": m.exclude_notes,
            "updated_at": m.updated_at,
        }


class DxEventObservationSerializer(serializers.ModelSerializer):
    observer = DxManagedNodeMinimalSerializer(read_only=True)

    class Meta:
        model = DxEventObservation
        fields = (
            "id",
            "observed_at",
            "distance_km",
            "metadata",
            "observer",
            "raw_packet",
            "packet_observation",
        )


class DxObservedNodeHopSerializer(serializers.ModelSerializer):
    """Destination (or hop target) without nested dx_metadata — used on exploration rows."""

    class Meta:
        model = ObservedNode
        fields = ("internal_id", "node_id", "node_id_str", "short_name", "long_name")


class DxAutoTracerouteExplorationSerializer(serializers.ModelSerializer):
    """Queued or completed AutoTraceRoute row when present on a DX exploration attempt."""

    trigger_type_label = serializers.SerializerMethodField()

    class Meta:
        model = AutoTraceRoute
        fields = (
            "id",
            "status",
            "trigger_type",
            "trigger_type_label",
            "trigger_source",
            "triggered_at",
            "earliest_send_at",
            "dispatched_at",
            "completed_at",
            "error_message",
        )

    def get_trigger_type_label(self, obj: AutoTraceRoute) -> str:
        labels = {
            int(AutoTraceRoute.TRIGGER_TYPE_USER): "User",
            int(AutoTraceRoute.TRIGGER_TYPE_EXTERNAL): "External",
            int(AutoTraceRoute.TRIGGER_TYPE_MONITORING): "Monitoring",
            int(AutoTraceRoute.TRIGGER_TYPE_NODE_WATCH): "Node watch",
            int(AutoTraceRoute.TRIGGER_TYPE_DX_WATCH): "DX Watch",
            int(AutoTraceRoute.TRIGGER_TYPE_NEW_NODE_BASELINE): "New node baseline",
        }
        return labels.get(int(obj.trigger_type), str(obj.trigger_type))


class DxEventTracerouteExplorationSerializer(serializers.ModelSerializer):
    """One DX exploration attempt: DX_WATCH queue, skip outcome, or linked new-node baseline."""

    auto_traceroute = DxAutoTracerouteExplorationSerializer(read_only=True, allow_null=True)
    source_node = DxManagedNodeMinimalSerializer(read_only=True, allow_null=True)
    destination = serializers.SerializerMethodField()
    link_kind = serializers.SerializerMethodField()

    class Meta:
        model = DxEventTraceroute
        fields = (
            "id",
            "outcome",
            "skip_reason",
            "metadata",
            "link_kind",
            "created_at",
            "updated_at",
            "source_node",
            "destination",
            "auto_traceroute",
        )

    def get_link_kind(self, obj: DxEventTraceroute) -> str:
        meta = obj.metadata or {}
        return str(meta.get("link_kind") or "")

    def get_destination(self, obj: DxEventTraceroute) -> dict:
        if obj.auto_traceroute_id:
            dest = obj.auto_traceroute.target_node
        else:
            dest = obj.event.destination
        return DxObservedNodeHopSerializer(dest, context=self.context).data


class DxEventListSerializer(serializers.ModelSerializer):
    constellation = ConstellationMinimalSerializer(read_only=True)
    destination = DxDestinationSerializer(read_only=True)
    last_observer = DxManagedNodeMinimalSerializer(read_only=True, allow_null=True)
    evidence_count = serializers.IntegerField(read_only=True)
    exploration_attempt_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = DxEvent
        fields = (
            "id",
            "constellation",
            "destination",
            "reason_code",
            "state",
            "first_observed_at",
            "last_observed_at",
            "active_until",
            "observation_count",
            "last_observer",
            "best_distance_km",
            "last_distance_km",
            "metadata",
            "evidence_count",
            "exploration_attempt_count",
        )


class DxEventDetailSerializer(DxEventListSerializer):
    observations = DxEventObservationSerializer(many=True, read_only=True)
    traceroute_explorations = DxEventTracerouteExplorationSerializer(many=True, read_only=True)
    exploration_summary = serializers.SerializerMethodField()

    class Meta(DxEventListSerializer.Meta):
        fields = DxEventListSerializer.Meta.fields + (
            "observations",
            "traceroute_explorations",
            "exploration_summary",
        )

    def get_exploration_summary(self, obj: DxEvent) -> dict:
        rows = list(obj.traceroute_explorations.all())
        by_outcome = Counter((r.outcome or "") for r in rows)
        baseline_rows = sum(1 for r in rows if (r.metadata or {}).get("link_kind") == "new_node_baseline")
        return {
            "total": len(rows),
            "pending": int(by_outcome.get("pending", 0)),
            "completed": int(by_outcome.get("completed", 0)),
            "failed": int(by_outcome.get("failed", 0)),
            "skipped": int(by_outcome.get("skipped", 0)),
            "baseline_linked_rows": baseline_rows,
        }


class DxNodeExclusionRequestSerializer(serializers.Serializer):
    node_id = serializers.IntegerField(min_value=1)
    exclude_from_detection = serializers.BooleanField()
    exclude_notes = serializers.CharField(required=False, allow_blank=True, default="")


class DxNodeExclusionResponseSerializer(serializers.Serializer):
    node_id = serializers.IntegerField()
    node_id_str = serializers.CharField()
    exclude_from_detection = serializers.BooleanField()
    exclude_notes = serializers.CharField()
    updated_at = serializers.DateTimeField(allow_null=True)


def _available_dx_notification_category_values() -> list[str]:
    return [
        c.value
        for c in (
            DxNotificationCategory.NEW_DISTANT_NODE,
            DxNotificationCategory.RETURNED_DX_NODE,
            DxNotificationCategory.DISTANT_OBSERVATION,
            DxNotificationCategory.TRACEROUTE_DISTANT_HOP,
            DxNotificationCategory.CONFIRMED_EVENT,
            DxNotificationCategory.EVENT_CLOSED_SUMMARY,
        )
    ]


class DiscordReadinessSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["verified", "not_linked", "needs_relink"])
    can_receive_dms = serializers.BooleanField()


class DxNotificationSettingsResponseSerializer(serializers.Serializer):
    """GET /api/dx/notifications/settings/"""

    enabled = serializers.BooleanField()
    all_categories = serializers.BooleanField()
    categories = serializers.ListField(
        child=serializers.ChoiceField(choices=[(v, v) for v in _available_dx_notification_category_values()]),
        allow_empty=True,
        required=True,
    )
    discord = DiscordReadinessSerializer()


class DxNotificationSettingsWriteSerializer(serializers.Serializer):
    """PUT/PATCH body for self-service notification preferences."""

    enabled = serializers.BooleanField(required=False)
    all_categories = serializers.BooleanField(required=False)
    categories = serializers.ListField(
        child=serializers.ChoiceField(choices=[(v, v) for v in _available_dx_notification_category_values()]),
        allow_empty=True,
        required=False,
    )

    def validate(self, attrs: dict) -> dict:
        all_cat = attrs.get("all_categories", True)
        cats = attrs.get("categories")
        if not all_cat and (not cats or len(cats) < 1):
            raise serializers.ValidationError(
                {"categories": ("When all_categories is false, provide at least one category in `categories`.")}
            )
        return attrs
