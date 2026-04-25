"""Serializers for AutoTraceRoute."""

from rest_framework import serializers

from common.mesh_node_helpers import meshtastic_id_to_hex
from constellations.models import Constellation
from nodes.models import ManagedNode, ObservedNode
from nodes.serializers import ManagedNodeSerializer, ObservedNodeSerializer, PositionSerializer

from .models import AutoTraceRoute, TriggerType

UNKNOWN_NODE_ID = 0xFFFFFFFF


def trigger_type_label_for(value: int) -> str:
    try:
        return str(TriggerType(value).label)
    except ValueError:
        return str(value)


class TracerouteListConstellationSerializer(serializers.ModelSerializer):
    """Minimal constellation for traceroute list source node."""

    class Meta:
        model = Constellation
        fields = ["id", "name", "map_color"]
        read_only_fields = fields


class TracerouteListSourceNodeSerializer(serializers.ModelSerializer):
    """Minimal ManagedNode for list view; short_name from bulk-prefetched context."""

    short_name = serializers.SerializerMethodField()
    node_id_str = serializers.SerializerMethodField()
    constellation = TracerouteListConstellationSerializer(read_only=True)

    class Meta:
        model = ManagedNode
        fields = ["node_id", "name", "short_name", "node_id_str", "constellation", "allow_auto_traceroute"]
        read_only_fields = fields

    def get_short_name(self, obj):
        observed = self.context.get("observed_short_names") if self.context else {}
        return observed.get(obj.node_id, obj.name)

    def get_node_id_str(self, obj):
        return meshtastic_id_to_hex(obj.node_id)


class TracerouteTargetNodeSerializer(serializers.ModelSerializer):
    """Minimal ObservedNode for traceroute list; latest_position from latest_status, claim from context."""

    latest_position = serializers.SerializerMethodField()
    claim = serializers.SerializerMethodField()

    class Meta:
        model = ObservedNode
        fields = [
            "internal_id",
            "node_id",
            "node_id_str",
            "long_name",
            "short_name",
            "last_heard",
            "latest_position",
            "claim",
        ]
        read_only_fields = fields

    def get_latest_position(self, obj):
        status = getattr(obj, "latest_status", None)
        if status is None or (
            status.position_reported_time is None and status.latitude is None and status.longitude is None
        ):
            return None
        data = {
            "latest_latitude": status.latitude,
            "latest_longitude": status.longitude,
            "latest_altitude": status.altitude,
            "latest_position_time": status.position_reported_time,
            "latest_heading": status.heading,
            "latest_location_source": status.location_source,
            "latest_precision_bits": status.precision_bits,
            "latest_ground_speed": status.ground_speed,
            "latest_ground_track": status.ground_track,
            "latest_sats_in_view": status.sats_in_view,
            "latest_pdop": status.pdop,
            "node": obj.internal_id,
        }
        return PositionSerializer(data).data

    def get_claim(self, obj):
        claims = self.context.get("user_claims_by_node") if self.context else {}
        claim = claims.get(obj.internal_id)
        if not claim:
            return None
        return {"created_at": claim.created_at, "accepted_at": claim.accepted_at}


class TracerouteSourceNodeSerializer(ManagedNodeSerializer):
    """ManagedNode serializer with short_name from ObservedNode (traceroute context has no annotation)."""

    short_name = serializers.SerializerMethodField()

    def get_short_name(self, obj):
        obs = ObservedNode.objects.filter(node_id=obj.node_id).values_list("short_name", flat=True).first()
        return obs if obs is not None else obj.name


def _enrich_route_nodes(route_data, observed_by_id=None):
    """Convert route/route_back list of {node_id, snr} to enriched list with position.

    If observed_by_id is provided (pre-fetched for batch), use it. Otherwise fetch per-call.
    """
    if not route_data:
        return []
    node_ids = [item["node_id"] for item in route_data]
    if observed_by_id is None:
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


class TracerouteListSerializer(serializers.ModelSerializer):
    """Optimized serializer for traceroute list view; uses lightweight source/target and bulk-prefetch context."""

    source_node = TracerouteListSourceNodeSerializer(read_only=True)
    target_node = TracerouteTargetNodeSerializer(read_only=True)
    triggered_by_username = serializers.CharField(source="triggered_by.username", read_only=True)
    trigger_type_label = serializers.SerializerMethodField()
    route_nodes = serializers.SerializerMethodField()
    route_back_nodes = serializers.SerializerMethodField()

    class Meta:
        model = AutoTraceRoute
        fields = [
            "id",
            "source_node",
            "target_node",
            "trigger_type",
            "trigger_type_label",
            "triggered_by",
            "triggered_by_username",
            "trigger_source",
            "triggered_at",
            "earliest_send_at",
            "dispatched_at",
            "dispatch_attempts",
            "dispatch_error",
            "status",
            "route",
            "route_back",
            "route_nodes",
            "route_back_nodes",
            "raw_packet",
            "completed_at",
            "error_message",
            "target_strategy",
        ]
        read_only_fields = fields

    def get_trigger_type_label(self, obj):
        return trigger_type_label_for(obj.trigger_type)

    def get_route_nodes(self, obj):
        observed = self.context.get("observed_by_id") if self.context else None
        return _enrich_route_nodes(obj.route, observed) if obj.route else []

    def get_route_back_nodes(self, obj):
        observed = self.context.get("observed_by_id") if self.context else None
        return _enrich_route_nodes(obj.route_back, observed) if obj.route_back else []


class AutoTraceRouteSerializer(serializers.ModelSerializer):
    """Serializer for AutoTraceRoute detail and trigger responses."""

    source_node = TracerouteSourceNodeSerializer(read_only=True)
    target_node = ObservedNodeSerializer(read_only=True)
    triggered_by_username = serializers.CharField(source="triggered_by.username", read_only=True)
    trigger_type_label = serializers.SerializerMethodField()
    route_nodes = serializers.SerializerMethodField()
    route_back_nodes = serializers.SerializerMethodField()

    class Meta:
        model = AutoTraceRoute
        fields = [
            "id",
            "source_node",
            "target_node",
            "trigger_type",
            "trigger_type_label",
            "triggered_by",
            "triggered_by_username",
            "trigger_source",
            "triggered_at",
            "earliest_send_at",
            "dispatched_at",
            "dispatch_attempts",
            "dispatch_error",
            "status",
            "route",
            "route_back",
            "route_nodes",
            "route_back_nodes",
            "raw_packet",
            "completed_at",
            "error_message",
            "target_strategy",
        ]
        read_only_fields = fields

    def get_trigger_type_label(self, obj):
        return trigger_type_label_for(obj.trigger_type)

    def get_route_nodes(self, obj):
        observed = self.context.get("observed_by_id") if self.context else None
        return _enrich_route_nodes(obj.route, observed) if obj.route else []

    def get_route_back_nodes(self, obj):
        observed = self.context.get("observed_by_id") if self.context else None
        return _enrich_route_nodes(obj.route_back, observed) if obj.route_back else []


class TriggerableNodeSerializer(serializers.ModelSerializer):
    """Minimal ManagedNode for triggerable-nodes list; short_name/long_name from ObservedNode annotation."""

    node_id_str = serializers.SerializerMethodField()
    short_name = serializers.SerializerMethodField()
    long_name = serializers.SerializerMethodField()
    constellation = TracerouteListConstellationSerializer(read_only=True)
    position = serializers.SerializerMethodField()

    class Meta:
        model = ManagedNode
        fields = [
            "node_id",
            "node_id_str",
            "short_name",
            "long_name",
            "allow_auto_traceroute",
            "constellation",
            "position",
        ]
        read_only_fields = fields

    def get_node_id_str(self, obj):
        return meshtastic_id_to_hex(obj.node_id)

    def get_short_name(self, obj):
        return getattr(obj, "observed_short_name", None) or obj.name

    def get_long_name(self, obj):
        return getattr(obj, "observed_long_name", None) or obj.name

    def get_position(self, obj):
        # Prefer the latest observed position (annotated from NodeLatestStatus);
        # fall back to the ManagedNode's configured default location so the UI
        # can still place nodes that have never been heard.
        lat = getattr(obj, "observed_latitude", None)
        lng = getattr(obj, "observed_longitude", None)
        if lat is None and lng is None:
            lat = obj.default_location_latitude
            lng = obj.default_location_longitude
        return {"latitude": lat, "longitude": lng}


class TriggerTracerouteSerializer(serializers.Serializer):
    """Serializer for POST /api/traceroutes/trigger/."""

    managed_node_id = serializers.IntegerField(help_text="Node ID of the ManagedNode (source/bot)")
    target_node_id = serializers.IntegerField(
        required=False, allow_null=True, help_text="Target ObservedNode node_id (optional for auto)"
    )
    target_strategy = serializers.ChoiceField(
        choices=[
            AutoTraceRoute.TARGET_STRATEGY_INTRA_ZONE,
            AutoTraceRoute.TARGET_STRATEGY_DX_ACROSS,
            AutoTraceRoute.TARGET_STRATEGY_DX_SAME_SIDE,
        ],
        required=False,
        allow_null=True,
        help_text=(
            "Optional hypothesis selector when auto-picking target. Omit to let the server pick via LRU. "
            "When target_node_id is set, this field is ignored and the row is stored as strategy=manual."
        ),
    )
