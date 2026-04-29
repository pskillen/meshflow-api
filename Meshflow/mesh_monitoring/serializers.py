"""DRF serializers for mesh monitoring."""

from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from mesh_monitoring.constants import DEFAULT_OFFLINE_AFTER_SECONDS
from mesh_monitoring.eligibility import user_can_watch
from mesh_monitoring.models import NodeMonitoringConfig, NodeWatch
from nodes.models import ObservedNode
from nodes.serializers import ObservedNodeSerializer


def _last_heard_offline_after_seconds_for_observed_node(obj: ObservedNode) -> int:
    cfg = getattr(obj, "monitoring_config", None)
    if cfg is not None:
        return int(cfg.last_heard_offline_after_seconds)
    return int(DEFAULT_OFFLINE_AFTER_SECONDS)


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
        return _last_heard_offline_after_seconds_for_observed_node(obj)


class NodeMonitoringConfigSerializer(serializers.ModelSerializer):
    """Read/write NodeMonitoringConfig; presence-derived fields are read-only."""

    editable = serializers.SerializerMethodField()
    battery_alert_active = serializers.SerializerMethodField()
    battery_alert_confirmed_at = serializers.SerializerMethodField()

    class Meta:
        model = NodeMonitoringConfig
        fields = [
            "last_heard_offline_after_seconds",
            "battery_alert_enabled",
            "battery_alert_threshold_percent",
            "battery_alert_report_count",
            "editable",
            "battery_alert_active",
            "battery_alert_confirmed_at",
        ]
        read_only_fields = ["editable", "battery_alert_active", "battery_alert_confirmed_at"]

    def get_editable(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        from mesh_monitoring.permission_helpers import user_can_edit_node_monitoring_config

        return user_can_edit_node_monitoring_config(request.user, obj.observed_node)

    def get_battery_alert_active(self, obj):
        rel = getattr(obj.observed_node, "mesh_presence", None)
        if rel is None:
            return False
        return bool(obj.battery_alert_enabled and rel.battery_alert_confirmed_at is not None)

    def get_battery_alert_confirmed_at(self, obj):
        rel = getattr(obj.observed_node, "mesh_presence", None)
        if rel is None:
            return None
        return rel.battery_alert_confirmed_at

    def validate_last_heard_offline_after_seconds(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError(_("last_heard_offline_after_seconds must be at least 1 second."))
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
            "offline_notifications_enabled",
            "battery_notifications_enabled",
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
        return _last_heard_offline_after_seconds_for_observed_node(obj.observed_node)
