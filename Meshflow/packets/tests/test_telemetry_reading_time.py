"""Telemetry without a usable ``time`` falls back to the packet's rx_time (#478)."""

from datetime import datetime, timezone

import packets.serializers as ser
from packets.models import DeviceMetricsPacket
from packets.serializers import PacketIngestSerializer
from packets.tests.test_packet_serializers import BasePacketSerializerTestCase, assert_serializer_valid

RX = 1672531200
RX_DT = datetime(2023, 1, 1, tzinfo=timezone.utc)

VARIANTS = [
    ("deviceMetrics", "DeviceMetricsPacketSerializer"),
    ("localStats", "LocalStatsPacketSerializer"),
    ("environmentMetrics", "EnvironmentMetricsPacketSerializer"),
    ("airQualityMetrics", "AirQualityMetricsPacketSerializer"),
    ("powerMetrics", "PowerMetricsPacketSerializer"),
    ("healthMetrics", "HealthMetricsPacketSerializer"),
    ("hostMetrics", "HostMetricsPacketSerializer"),
    ("trafficManagementStats", "TrafficManagementStatsPacketSerializer"),
]

TIME_CASES = (("absent", {}), ("zero", {"time": 0}), ("null", {"time": None}))


class TelemetryReadingTimeFallbackTest(BasePacketSerializerTestCase):
    def _data(self, variant, packet_id=321, **time_kwargs):
        telemetry = {variant: {}}
        telemetry.update(time_kwargs)
        return {
            "id": packet_id,
            "from": self.from_node.meshtastic_node_id,
            "fromId": self.from_node.node_id_str,
            "decoded": {"portnum": "TELEMETRY_APP", "telemetry": telemetry},
            "rxTime": RX,
        }

    def test_all_variants_fall_back_to_rx_time(self):
        for variant, cls_name in VARIANTS:
            for label, kwargs in TIME_CASES:
                with self.subTest(variant=variant, time=label):
                    serializer = getattr(ser, cls_name)(data=self._data(variant, **kwargs), context=self.context)
                    assert_serializer_valid(serializer)
                    self.assertEqual(serializer.validated_data["reading_time"], RX_DT)

    def test_all_variants_keep_explicit_time(self):
        for variant, cls_name in VARIANTS:
            with self.subTest(variant=variant):
                serializer = getattr(ser, cls_name)(data=self._data(variant, time=1672617600), context=self.context)
                assert_serializer_valid(serializer)
                self.assertEqual(serializer.validated_data["reading_time"], datetime(2023, 1, 2, tzinfo=timezone.utc))

    def test_ingest_without_time_stores_packet_with_rx_time(self):
        for i, (label, kwargs) in enumerate(TIME_CASES):
            with self.subTest(time=label):
                data = self._data("deviceMetrics", packet_id=900 + i, **kwargs)
                serializer = PacketIngestSerializer(data=data, context=self.context)
                assert_serializer_valid(serializer)
                packet = serializer.save()
                self.assertIsInstance(packet, DeviceMetricsPacket)
                self.assertEqual(packet.reading_time, RX_DT)
