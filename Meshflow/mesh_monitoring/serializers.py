"""DRF serializers for mesh monitoring."""

from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from mesh_monitoring.eligibility import user_can_watch
from mesh_monitoring.models import NodeWatch
from nodes.models import ObservedNode


class ObservedNodeWatchSummarySerializer(serializers.ModelSerializer):
    """Minimal observed node + monitoring presence hints for watch payloads."""

    monitoring_verification_started_at = serializers.SerializerMethodField()
    monitoring_offline_confirmed_at = serializers.SerializerMethodField()

    class Meta:
        model = ObservedNode
        fields = [
            "internal_id",
            "node_id_str",
            "long_name",
            "last_heard",
            "monitoring_verification_started_at",
            "monitoring_offline_confirmed_at",
        ]

    def get_monitoring_verification_started_at(self, obj):
        rel = getattr(obj, "mesh_presence", None)
        if rel is None:
            return None
        return rel.verification_started_at

    def get_monitoring_offline_confirmed_at(self, obj):
        rel = getattr(obj, "mesh_presence", None)
        if rel is None:
            return None
        return rel.offline_confirmed_at


class NodeWatchSerializer(serializers.ModelSerializer):
    observed_node = ObservedNodeWatchSummarySerializer(read_only=True)
    observed_node_id = serializers.PrimaryKeyRelatedField(
        queryset=ObservedNode.objects.all(),
        source="observed_node",
        write_only=True,
        required=False,
    )

    class Meta:
        model = NodeWatch
        fields = [
            "id",
            "observed_node",
            "observed_node_id",
            "offline_after",
            "enabled",
            "created_at",
        ]
        read_only_fields = ["id", "observed_node", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is None:
            self.fields["observed_node_id"].required = True
        else:
            self.fields["observed_node_id"].read_only = True

    def validate_observed_node_id(self, value):
        request = self.context.get("request")
        if request and request.user.is_authenticated and value is not None:
            if not user_can_watch(request.user, value):
                raise serializers.ValidationError(
                    _("You may only watch nodes you claimed or infrastructure nodes."),
                )
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        observed = attrs.get("observed_node")
        if self.instance is None and observed is not None and request and request.user.is_authenticated:
            if NodeWatch.objects.filter(user=request.user, observed_node=observed).exists():
                raise serializers.ValidationError(
                    {"observed_node_id": _("You already have a watch for this node.")},
                )
        return attrs

    def validate_offline_after(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError(_("offline_after must be at least 1 second."))
        return value
