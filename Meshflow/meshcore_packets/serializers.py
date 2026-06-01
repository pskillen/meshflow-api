"""Serializers for MeshCore packet ingest."""

from datetime import datetime, timezone

from rest_framework import serializers

from common.meshcore_node_helpers import normalize_mc_pubkey, normalize_mc_pubkey_prefix
from meshcore_packets.models import (
    MeshCorePacketObservation,
    MeshCorePayloadType,
    MeshCoreRawPacket,
    MeshCoreTextPacket,
)
from meshcore_packets.services.channel import resolve_mc_channel
from meshcore_packets.services.dedup import find_existing_packet


def _parse_rx_time(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    try:
        ts = float(value)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError, OSError) as exc:
        raise serializers.ValidationError({"rx_time": f"Invalid rx_time: {exc}"}) from exc


class MeshCorePacketIngestSerializer(serializers.Serializer):
    """Bot envelope for MeshCore ingest."""

    event_type = serializers.CharField(max_length=64)
    payload_type = serializers.ChoiceField(
        choices=["advert", "channel_text", "contact_text", "raw"],
    )
    pkt_hash = serializers.IntegerField(required=False, allow_null=True)
    rx_time = serializers.JSONField()
    rx_rssi = serializers.FloatField(required=False, allow_null=True)
    rx_snr = serializers.FloatField(required=False, allow_null=True)
    from_pubkey = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    from_pubkey_prefix = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    to_pubkey_prefix = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    route_typename = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    path_hashes = serializers.JSONField(required=False, allow_null=True)
    path_hash_size = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=8)
    path_hash_mode = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=255)
    channel_idx = serializers.IntegerField(required=False, allow_null=True)
    text = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    adv_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    adv_lat = serializers.FloatField(required=False, allow_null=True)
    adv_lon = serializers.FloatField(required=False, allow_null=True)
    raw = serializers.JSONField(required=False)

    observation: MeshCorePacketObservation | None = None

    def validate(self, attrs):
        payload_type = attrs["payload_type"]
        if payload_type in ("channel_text", "contact_text") and not attrs.get("text"):
            raise serializers.ValidationError({"text": "Required for text payload types"})
        if payload_type == "advert" and not attrs.get("from_pubkey") and not attrs.get("from_pubkey_prefix"):
            if attrs.get("event_type") != "channel_message":
                pass  # rx_log_data ADVERT may supply adv fields without from_pubkey in envelope
        return attrs

    def create(self, validated_data):
        observer = self.context["observer"]
        rx_time = _parse_rx_time(validated_data["rx_time"])

        from_pubkey = validated_data.get("from_pubkey") or None
        from_prefix = validated_data.get("from_pubkey_prefix") or None
        if from_pubkey:
            from_pubkey = normalize_mc_pubkey(from_pubkey)
            from_prefix = from_pubkey[:12]
        elif from_prefix:
            from_prefix = normalize_mc_pubkey_prefix(from_prefix)

        pkt_hash = validated_data.get("pkt_hash")
        existing = find_existing_packet(
            pkt_hash=pkt_hash,
            rx_time=rx_time,
            event_type=validated_data.get("event_type"),
            raw_payload=str(validated_data.get("raw", "")),
        )
        if existing:
            self.instance = existing
            self._ensure_observation(existing, observer, validated_data, rx_time)
            return existing

        payload_type_map = {
            "advert": MeshCorePayloadType.ADVERT,
            "channel_text": MeshCorePayloadType.CHANNEL_TEXT,
            "contact_text": MeshCorePayloadType.CONTACT_TEXT,
            "raw": MeshCorePayloadType.RAW,
        }
        ptype = payload_type_map[validated_data["payload_type"]]
        channel_idx = validated_data.get("channel_idx")
        channel = resolve_mc_channel(observer, channel_idx) if channel_idx is not None else None

        base_fields = {
            "observer": observer,
            "payload_type": ptype,
            "event_type": validated_data["event_type"],
            "from_pubkey": from_pubkey,
            "from_pubkey_prefix": from_prefix,
            "pkt_hash": pkt_hash,
            "rx_time": rx_time,
            "rx_rssi": validated_data.get("rx_rssi"),
            "rx_snr": validated_data.get("rx_snr"),
            "route_typename": validated_data.get("route_typename"),
            "raw_json": validated_data,
        }

        if ptype in (MeshCorePayloadType.CHANNEL_TEXT, MeshCorePayloadType.CONTACT_TEXT):
            to_prefix = validated_data.get("to_pubkey_prefix")
            if to_prefix:
                to_prefix = normalize_mc_pubkey_prefix(to_prefix)
            packet = MeshCoreTextPacket.objects.create(
                **base_fields,
                to_pubkey_prefix=to_prefix,
                channel=channel,
                text=validated_data.get("text") or "",
            )
        else:
            packet = MeshCoreRawPacket.objects.create(**base_fields)

        self.instance = packet
        self._ensure_observation(packet, observer, validated_data, rx_time)
        return packet

    def _ensure_observation(self, packet, observer, validated_data, rx_time):
        channel_idx = validated_data.get("channel_idx")
        channel = resolve_mc_channel(observer, channel_idx) if channel_idx is not None else None
        path_hashes = validated_data.get("path_hashes")
        obs, _ = MeshCorePacketObservation.objects.update_or_create(
            packet=packet,
            observer=observer,
            defaults={
                "channel": channel,
                "rx_time": rx_time,
                "rx_rssi": validated_data.get("rx_rssi"),
                "rx_snr": validated_data.get("rx_snr"),
                "path_hashes": path_hashes,
                "path_hash_size": validated_data.get("path_hash_size"),
                "path_hash_mode": validated_data.get("path_hash_mode"),
            },
        )
        self.observation = obs


class MeshCorePacketListSerializer(serializers.ModelSerializer):
    """Read serializer for MeshCore packet list."""

    observer_name = serializers.CharField(source="observer.name", read_only=True)
    text = serializers.SerializerMethodField()

    class Meta:
        model = MeshCoreRawPacket
        fields = [
            "id",
            "payload_type",
            "event_type",
            "from_pubkey",
            "from_pubkey_prefix",
            "pkt_hash",
            "rx_time",
            "rx_rssi",
            "rx_snr",
            "route_typename",
            "first_reported_time",
            "observer_name",
            "text",
        ]

    def get_text(self, obj):
        if hasattr(obj, "meshcoretextpacket"):
            return obj.meshcoretextpacket.text
        return None
