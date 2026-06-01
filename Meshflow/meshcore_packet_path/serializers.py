"""Read serializers for MeshCore passive packet path APIs."""

from rest_framework import serializers

from common.protocol import Protocol
from meshcore_packet_path.models import (
    MeshCorePathEdgeBucket,
    MeshCorePathSegmentResolution,
    SegmentStatus,
)
from nodes.models import ObservedNode


class MeshCorePathEdgeBucketSerializer(serializers.ModelSerializer):
    direction = serializers.SerializerMethodField()
    observer_name = serializers.CharField(source="observer.name", read_only=True, allow_null=True)
    constellation_name = serializers.CharField(
        source="constellation.name",
        read_only=True,
        allow_null=True,
    )
    resolved = serializers.SerializerMethodField()

    class Meta:
        model = MeshCorePathEdgeBucket
        fields = [
            "id",
            "bucket_start",
            "bucket_size",
            "from_kind",
            "to_kind",
            "from_hash",
            "to_hash",
            "from_node",
            "to_node",
            "observer",
            "observer_name",
            "constellation",
            "constellation_name",
            "packet_count",
            "observation_count",
            "first_seen_at",
            "last_seen_at",
            "avg_snr",
            "min_snr",
            "max_snr",
            "direction",
            "resolved",
        ]
        read_only_fields = fields

    def get_direction(self, obj) -> str:
        return "list_order"

    def get_resolved(self, obj) -> bool:
        return bool(obj.from_node_id and obj.to_node_id)


class ObservedNodeMinimalSerializer(serializers.ModelSerializer):
    node_id_str = serializers.SerializerMethodField()

    class Meta:
        model = ObservedNode
        fields = ["internal_id", "node_id_str", "long_name"]
        read_only_fields = fields

    def get_node_id_str(self, obj) -> str | None:
        if obj.protocol == Protocol.MESHCORE and obj.mc_pubkey:
            return f"mc:{obj.mc_pubkey}"
        return None


class MeshCorePathSegmentSerializer(serializers.ModelSerializer):
    observed_node = ObservedNodeMinimalSerializer(read_only=True)

    class Meta:
        model = MeshCorePathSegmentResolution
        fields = [
            "id",
            "segment_hash",
            "hash_size",
            "hash_mode",
            "status",
            "source",
            "resolver_version",
            "confidence",
            "observed_node",
            "first_seen_at",
            "last_seen_at",
        ]
        read_only_fields = fields


class MeshCorePathSegmentAnnotateSerializer(serializers.Serializer):
    """Staff manual annotation for a path segment."""

    observed_node_id = serializers.UUIDField(required=False, allow_null=True)
    node_id_str = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    status = serializers.ChoiceField(
        choices=SegmentStatus.choices,
        required=False,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one field is required")
        node_uuid = attrs.get("observed_node_id")
        node_id_str = attrs.get("node_id_str")
        if node_uuid and node_id_str:
            raise serializers.ValidationError("Provide observed_node_id or node_id_str, not both")
        return attrs

    def resolve_observed_node(self) -> ObservedNode | None:
        node_uuid = self.validated_data.get("observed_node_id")
        node_id_str = (self.validated_data.get("node_id_str") or "").strip()
        if node_uuid:
            return ObservedNode.objects.filter(
                internal_id=node_uuid,
                protocol=Protocol.MESHCORE,
            ).first()
        if node_id_str:
            pubkey = node_id_str.removeprefix("mc:").lower()
            return ObservedNode.objects.filter(
                protocol=Protocol.MESHCORE,
                mc_pubkey=pubkey,
            ).first()
        if "observed_node_id" in self.validated_data and self.validated_data["observed_node_id"] is None:
            return None
        if node_id_str == "" and "node_id_str" in self.validated_data:
            return None
        return None
