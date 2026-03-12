"""Serializers for AutoTraceRoute."""

from rest_framework import serializers

from nodes.serializers import ManagedNodeSerializer, ObservedNodeSerializer

from .models import AutoTraceRoute


class AutoTraceRouteSerializer(serializers.ModelSerializer):
    """Serializer for AutoTraceRoute list and detail."""

    source_node = ManagedNodeSerializer(read_only=True)
    target_node = ObservedNodeSerializer(read_only=True)
    triggered_by_username = serializers.CharField(source="triggered_by.username", read_only=True)

    class Meta:
        model = AutoTraceRoute
        fields = [
            "id",
            "source_node",
            "target_node",
            "trigger_type",
            "triggered_by",
            "triggered_by_username",
            "trigger_source",
            "triggered_at",
            "status",
            "route",
            "route_back",
            "raw_packet",
            "completed_at",
            "error_message",
        ]
        read_only_fields = fields


class TriggerTracerouteSerializer(serializers.Serializer):
    """Serializer for POST /api/traceroutes/trigger/."""

    managed_node_id = serializers.IntegerField(help_text="Node ID of the ManagedNode (source/bot)")
    target_node_id = serializers.IntegerField(required=False, allow_null=True, help_text="Target ObservedNode node_id (optional for auto)")
