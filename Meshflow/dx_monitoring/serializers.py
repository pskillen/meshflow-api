"""Serializers for DX monitoring visibility API."""

from rest_framework import serializers

from common.mesh_node_helpers import meshtastic_id_to_hex
from constellations.models import Constellation
from dx_monitoring.models import DxEvent, DxEventObservation, DxNodeMetadata
from nodes.models import ManagedNode, ObservedNode


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


class DxEventListSerializer(serializers.ModelSerializer):
    constellation = ConstellationMinimalSerializer(read_only=True)
    destination = DxDestinationSerializer(read_only=True)
    last_observer = DxManagedNodeMinimalSerializer(read_only=True, allow_null=True)
    evidence_count = serializers.IntegerField(read_only=True)

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
        )


class DxEventDetailSerializer(DxEventListSerializer):
    observations = DxEventObservationSerializer(many=True, read_only=True)

    class Meta(DxEventListSerializer.Meta):
        fields = DxEventListSerializer.Meta.fields + ("observations",)


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
