from rest_framework import serializers

from common.protocol import Protocol
from constellations.models import MessageChannel
from meshcore_packets.models import MeshCorePacketObservation
from nodes.models import ObservedNode
from packets.models import PacketObservation
from packets.serializers import PrefetchedPacketObservationSerializer

from .models import TextMessage


class TextMessageSerializer(serializers.ModelSerializer):
    """Mesh text message (Meshtastic or MeshCore)."""

    class ObservedNodeSerializer(serializers.ModelSerializer):
        class Meta:
            model = ObservedNode
            fields = ["node_id_str", "long_name", "short_name"]

    sender = ObservedNodeSerializer(read_only=True, allow_null=True)
    channel = serializers.PrimaryKeyRelatedField(queryset=MessageChannel.objects.all())
    heard = serializers.SerializerMethodField()
    packet_id = serializers.SerializerMethodField()
    protocol = serializers.SerializerMethodField()

    def get_protocol(self, obj):
        return Protocol(obj.protocol).label.lower()

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
        if obj.protocol == Protocol.MESHCORE and obj.original_mc_packet_id:
            observations = MeshCorePacketObservation.objects.filter(
                packet_id=obj.original_mc_packet_id,
            ).select_related("observer")
            return [
                {
                    "observer": obs.observer.node_id_str,
                    "rx_time": obs.rx_time,
                    "rx_rssi": obs.rx_rssi,
                    "rx_snr": obs.rx_snr,
                }
                for obs in observations
            ]

        if hasattr(obj.original_packet, "prefetched_observations"):
            observations = obj.original_packet.prefetched_observations
            return PrefetchedPacketObservationSerializer(observations, many=True, context=self.context).data
        return []
