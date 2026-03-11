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


class NeighbourStatsCandidateSerializer(serializers.Serializer):
    """Serializer for a candidate node matching a source."""

    node_id = serializers.IntegerField()
    node_id_str = serializers.CharField(allow_blank=True)
    short_name = serializers.CharField(allow_null=True, allow_blank=True)


class NeighbourStatsSerializer(serializers.Serializer):
    """Serializer for neighbour (by-source) stats response."""

    class BySourceSerializer(serializers.Serializer):
        """Serializer for a single source's packet count and candidate nodes."""

        source = serializers.IntegerField()
        source_type = serializers.ChoiceField(choices=["lsb", "full"])
        count = serializers.IntegerField()
        candidates = NeighbourStatsCandidateSerializer(many=True)

    start_date = serializers.DateTimeField(allow_null=True)
    end_date = serializers.DateTimeField(allow_null=True)
    by_source = BySourceSerializer(many=True)
    total_packets = serializers.IntegerField()


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
