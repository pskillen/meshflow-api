from rest_framework import serializers

from common.protocol import Protocol
from constellations.models import MessageChannel
from meshcore_packets.models import MeshCorePacketObservation
from meshcore_packets.services.path_resolution import format_path_hops, path_known_for_segments
from nodes.models import ManagedNode, ObservedNode
from packets.serializers import PrefetchedPacketObservationSerializer

from .map_helpers import managed_node_map_position, observed_node_map_position
from .models import TextMessage


def _normalize_path_segment(segment) -> str:
    return str(segment).strip().lower().replace("0x", "")


def _resolved_path_from_cache(segments, cache):
    if not segments:
        return []
    hops = []
    for segment in segments:
        key = _normalize_path_segment(segment)
        hop = cache.get(key) if cache else None
        if hop is None:
            hop = format_path_hops([segment])[0]
        hops.append(hop)
    return hops


def _mc_heard_observer(managed_node: ManagedNode, mc_observed_by_pubkey: dict) -> dict:
    observed = None
    if managed_node.mc_pubkey:
        observed = mc_observed_by_pubkey.get(managed_node.mc_pubkey.lower())
    return {
        "node_id_str": managed_node.node_id_str,
        "internal_id": str(observed.id) if observed else None,
        "long_name": observed.long_name if observed else managed_node.name,
        "short_name": observed.short_name if observed else managed_node.node_id_str,
        "position": managed_node_map_position(managed_node),
    }


class TextMessageSerializer(serializers.ModelSerializer):
    """Mesh text message (Meshtastic or MeshCore)."""

    class ObservedNodeSerializer(serializers.ModelSerializer):
        class Meta:
            model = ObservedNode
            fields = ["node_id_str", "long_name", "short_name"]

    sender = ObservedNodeSerializer(read_only=True, allow_null=True)
    sender_position = serializers.SerializerMethodField()
    channel = serializers.PrimaryKeyRelatedField(queryset=MessageChannel.objects.all())
    heard = serializers.SerializerMethodField()
    packet_id = serializers.SerializerMethodField()
    protocol = serializers.SerializerMethodField()

    def get_protocol(self, obj):
        return Protocol(obj.protocol).label.lower()

    def get_sender_position(self, obj):
        return observed_node_map_position(obj.sender) if obj.sender_id else None

    def get_packet_id(self, obj):
        if obj.original_packet_id:
            return obj.original_packet.packet_id
        if obj.original_mc_packet_id:
            mc = obj.original_mc_packet
            return mc.pkt_hash if mc.pkt_hash is not None else str(mc.id)
        return None

    class Meta:
        model = TextMessage
        fields = [
            "id",
            "protocol",
            "original_packet_id",
            "original_mc_packet_id",
            "packet_id",
            "sender",
            "sender_position",
            "recipient_meshtastic_node_id",
            "channel",
            "sent_at",
            "message_text",
            "is_emoji",
            "reply_to_meshtastic_packet_id",
            "heard",
        ]
        read_only_fields = fields

    def get_heard(self, obj):
        path_hop_cache = self.context.get("path_hop_cache") or {}
        mc_observed_by_pubkey = self.context.get("mc_observed_by_pubkey") or {}

        if obj.protocol == Protocol.MESHCORE and obj.original_mc_packet_id:
            packet = obj.original_mc_packet
            observations = getattr(packet, "prefetched_mc_observations", None)
            if observations is None:
                observations = MeshCorePacketObservation.objects.filter(packet_id=packet.id).select_related(
                    "observer",
                )
            heard = []
            for obs in observations:
                segments = obs.path_hashes or []
                heard.append(
                    {
                        "observer": _mc_heard_observer(obs.observer, mc_observed_by_pubkey),
                        "rx_time": obs.rx_time,
                        "rx_rssi": obs.rx_rssi,
                        "rx_snr": obs.rx_snr,
                        "path_hashes": segments,
                        "resolved_path": _resolved_path_from_cache(segments, path_hop_cache),
                        "path_known": path_known_for_segments(segments),
                    }
                )
            return heard

        if hasattr(obj.original_packet, "prefetched_observations"):
            observations = obj.original_packet.prefetched_observations
            return PrefetchedPacketObservationSerializer(observations, many=True, context=self.context).data
        return []
