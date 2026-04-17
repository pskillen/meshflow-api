"""DRF serializers for mesh monitoring."""

from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from mesh_monitoring.constants import DEFAULT_OFFLINE_AFTER_SECONDS
from mesh_monitoring.eligibility import user_can_watch
from mesh_monitoring.models import NodePresence, NodeWatch
from nodes.models import ObservedNode
from nodes.serializers import ObservedNodeSerializer


class ObservedNodeWatchSummarySerializer(ObservedNodeSerializer):
    """
    Observed node fields aligned with GET /nodes/observed-nodes/ plus mesh monitoring hints.

    Used only on NodeWatch responses so dashboards can render charts and controls without N+1 fetches.
    """

    monitoring_verification_started_at = serializers.SerializerMethodField()
    monitoring_offline_confirmed_at = serializers.SerializerMethodField()
    offline_after = serializers.SerializerMethodField()

    class Meta(ObservedNodeSerializer.Meta):
        fields = list(ObservedNodeSerializer.Meta.fields) + [
            "monitoring_verification_started_at",
            "monitoring_offline_confirmed_at",
            "offline_after",
        ]
        read_only_fields = list(ObservedNodeSerializer.Meta.read_only_fields) + [
            "monitoring_verification_started_at",
            "monitoring_offline_confirmed_at",
            "offline_after",
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

    def get_offline_after(self, obj):
        rel = getattr(obj, "mesh_presence", None)
        if rel is None:
            return DEFAULT_OFFLINE_AFTER_SECONDS
        return rel.offline_after


class NodePresenceOfflineAfterSerializer(serializers.ModelSerializer):
    """PATCH body for NodePresence.offline_after (node-level silence threshold)."""

    class Meta:
        model = NodePresence
        fields = ["offline_after"]

    def validate_offline_after(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError(_("offline_after must be at least 1 second."))
        return value


class NodeWatchSerializer(serializers.ModelSerializer):
    observed_node = ObservedNodeWatchSummarySerializer(read_only=True)
    offline_after = serializers.SerializerMethodField()
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
        read_only_fields = ["id", "observed_node", "offline_after", "created_at"]

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

    def get_offline_after(self, obj):
        rel = getattr(obj.observed_node, "mesh_presence", None)
        if rel is None:
            return DEFAULT_OFFLINE_AFTER_SECONDS
        return rel.offline_after
