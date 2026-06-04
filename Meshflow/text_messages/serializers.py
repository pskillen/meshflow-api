from rest_framework import serializers

from common.protocol import Protocol
from constellations.models import MessageChannel
from meshcore_packets.models import MeshCorePacketObservation
from meshcore_packets.services.path_resolution import (
    format_path_hops,
    path_known_for_segments,
    segment_identity_key,
)
from nodes.models import ManagedNode, ObservedNode
from packets.serializers import PrefetchedPacketObservationSerializer

from .map_helpers import managed_node_map_position, observed_node_map_position
from .mc_channel_sender import parse_mc_channel_sender_label
from .models import TextMessage


def _normalize_path_segment(segment) -> str:
    return str(segment).strip().lower().replace("0x", "")


def _resolved_path_from_cache(segments, cache, *, hash_mode=None, hash_size=None):
    if not segments:
        return []
    hops = []
    for segment in segments:
        key = segment_identity_key(segment, hash_mode, hash_size)
        hop = cache.get(key) if cache else None
        if hop is None:
            hop = format_path_hops([segment], hash_mode=hash_mode, hash_size=hash_size)[0]
        hops.append(hop)
    return hops


def _mc_heard_observer(managed_node: ManagedNode, mc_observed_by_pubkey: dict) -> dict:
    observed = None
    if managed_node.mc_pubkey:
        observed = mc_observed_by_pubkey.get(managed_node.mc_pubkey.lower())
    return {
        "node_id_str": managed_node.node_id_str,
        "internal_id": str(observed.internal_id) if observed else None,
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
    mc_sender_label = serializers.SerializerMethodField()
    mc_sender_candidates = serializers.SerializerMethodField()
    channel = serializers.PrimaryKeyRelatedField(queryset=MessageChannel.objects.all())
    heard = serializers.SerializerMethodField()
    packet_id = serializers.SerializerMethodField()
    protocol = serializers.SerializerMethodField()

    def get_protocol(self, obj):
        return Protocol(obj.protocol).label.lower()

    def get_sender_position(self, obj):
        if obj.sender_id:
            return observed_node_map_position(obj.sender)
        if obj.protocol == Protocol.MESHCORE:
            candidates = self.get_mc_sender_candidates(obj)
            if len(candidates) == 1 and candidates[0].get("position"):
                return candidates[0]["position"]
        return None

    def get_mc_sender_label(self, obj):
        if obj.protocol != Protocol.MESHCORE or obj.sender_id:
            return None
        return parse_mc_channel_sender_label(obj.message_text)

    def get_mc_sender_candidates(self, obj):
        if obj.protocol != Protocol.MESHCORE or obj.sender_id:
            return []
        cache = self.context.get("mc_sender_candidates_by_label")
        if cache is not None:
            label = parse_mc_channel_sender_label(obj.message_text)
            if not label:
                return []
            return cache.get(label, [])
        from .mc_channel_sender import mc_sender_candidates_for_message

        return mc_sender_candidates_for_message(obj.message_text)

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
            "mc_sender_label",
            "mc_sender_candidates",
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
                        "path_hash_mode": obs.path_hash_mode,
                        "path_hash_size": obs.path_hash_size,
                        "path_hashes": segments,
                        "resolved_path": _resolved_path_from_cache(
                            segments,
                            path_hop_cache,
                            hash_mode=obs.path_hash_mode,
                            hash_size=obs.path_hash_size,
                        ),
                        "path_known": path_known_for_segments(
                            segments,
                            hash_mode=obs.path_hash_mode,
                            hash_size=obs.path_hash_size,
                            resolution_cache=path_hop_cache,
                        ),
                    }
                )
            return heard

        if hasattr(obj.original_packet, "prefetched_observations"):
            observations = obj.original_packet.prefetched_observations
            return PrefetchedPacketObservationSerializer(observations, many=True, context=self.context).data
        return []
