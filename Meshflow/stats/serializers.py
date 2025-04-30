from rest_framework import serializers


class NodeStatsSerializer(serializers.Serializer):
    """Serializer for node stats response."""

    class IntervalSerializer(serializers.Serializer):
        """Serializer for node stats interval data."""

        class PacketTypeCountSerializer(serializers.Serializer):
            """Serializer for packet type counts."""

            packet_type = serializers.CharField()
            count = serializers.IntegerField()

        start_date = serializers.DateTimeField()
        end_date = serializers.DateTimeField()
        packet_types = PacketTypeCountSerializer(many=True)

    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    intervals = IntervalSerializer(many=True)


class GlobalStatsSerializer(serializers.Serializer):
    """Serializer for global stats response."""

    class IntervalSerializer(serializers.Serializer):
        """Serializer for global stats interval data."""

        start_date = serializers.DateTimeField()
        end_date = serializers.DateTimeField()
        packets = serializers.IntegerField()

    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    intervals = IntervalSerializer(many=True)
    summary = serializers.DictField()
