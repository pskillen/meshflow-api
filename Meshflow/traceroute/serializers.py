"""Serializers for AutoTraceRoute."""

from rest_framework import serializers

from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import ObservedNode
from nodes.serializers import ManagedNodeSerializer, ObservedNodeSerializer

from .models import AutoTraceRoute

UNKNOWN_NODE_ID = 0xFFFFFFFF


class TracerouteSourceNodeSerializer(ManagedNodeSerializer):
    """ManagedNode serializer with short_name from ObservedNode (traceroute context has no annotation)."""

    short_name = serializers.SerializerMethodField()

    def get_short_name(self, obj):
        obs = ObservedNode.objects.filter(node_id=obj.node_id).values_list("short_name", flat=True).first()
        return obs if obs is not None else obj.name


def _enrich_route_nodes(route_data):
    """Convert route/route_back list of {node_id, snr} to enriched list with position."""
    if not route_data:
        return []
    node_ids = [item["node_id"] for item in route_data]
    # Bulk fetch ObservedNodes with latest_status
    observed_by_id = {
        o.node_id: o for o in ObservedNode.objects.filter(node_id__in=node_ids).select_related("latest_status")
    }
    result = []
    for item in route_data:
        nid = item["node_id"]
        snr = item.get("snr")
        if nid == UNKNOWN_NODE_ID:
            result.append(
                {
                    "node_id": nid,
                    "node_id_str": "!ffffffff",
                    "short_name": "unknown",
                    "position": None,
                    "snr": snr,
                }
            )
            continue
        obs = observed_by_id.get(nid)
        if obs:
            pos = None
            if obs.latest_status and obs.latest_status.latitude is not None and obs.latest_status.longitude is not None:
                pos = {"latitude": obs.latest_status.latitude, "longitude": obs.latest_status.longitude}
            result.append(
                {
                    "node_id": obs.node_id,
                    "node_id_str": obs.node_id_str,
                    "short_name": obs.short_name,
                    "position": pos,
                    "snr": snr,
                }
            )
        else:
            result.append(
                {
                    "node_id": nid,
                    "node_id_str": meshtastic_id_to_hex(nid),
                    "short_name": None,
                    "position": None,
                    "snr": snr,
                }
            )
    return result


class AutoTraceRouteSerializer(serializers.ModelSerializer):
    """Serializer for AutoTraceRoute list and detail."""

    source_node = TracerouteSourceNodeSerializer(read_only=True)
    target_node = ObservedNodeSerializer(read_only=True)
    triggered_by_username = serializers.CharField(source="triggered_by.username", read_only=True)
    route_nodes = serializers.SerializerMethodField()
    route_back_nodes = serializers.SerializerMethodField()

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
            "route_nodes",
            "route_back_nodes",
            "raw_packet",
            "completed_at",
            "error_message",
        ]
        read_only_fields = fields

    def get_route_nodes(self, obj):
        return _enrich_route_nodes(obj.route) if obj.route else []

    def get_route_back_nodes(self, obj):
        return _enrich_route_nodes(obj.route_back) if obj.route_back else []


class TriggerTracerouteSerializer(serializers.Serializer):
    """Serializer for POST /api/traceroutes/trigger/."""

    managed_node_id = serializers.IntegerField(help_text="Node ID of the ManagedNode (source/bot)")
    target_node_id = serializers.IntegerField(
        required=False, allow_null=True, help_text="Target ObservedNode node_id (optional for auto)"
    )
