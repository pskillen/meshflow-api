"""Meshtastic 2.8 environment and air-quality telemetry fields (hand-built 2.8-shaped packets)."""

from django.urls import reverse

import pytest
from rest_framework.test import APIClient

from nodes.models import AirQualityMetrics, EnvironmentMetrics
from packets.models import AirQualityMetricsPacket, EnvironmentMetricsPacket, GenericPacket

NODE = 0x1A2B3C4D
RX = 1672531200

ENV_KEYS = {
    **{f"adcVoltageCh{i}": 0.5 + i for i in range(8)},
    **{f"oneWireTemperatureCh{i}": 10.25 + i for i in range(8)},
    "lightningStrikeCount1h": 4_000_000_000,
    "lightningDistanceKm": 12.5,
}
ENV_FIELDS = {
    **{f"adc_voltage_ch{i}": 0.5 + i for i in range(8)},
    **{f"one_wire_temperature_ch{i}": 10.25 + i for i in range(8)},
    "lightning_strike_count_1h": 4_000_000_000,
    "lightning_distance_km": 12.5,
}
PM_STATUS_FLAGS = 2**31 + 5


@pytest.fixture
def feeder(create_node_auth):
    auth = create_node_auth()
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=auth.api_key.key)
    return {"client": client, "node": auth.node}


def _ingest(feeder, variant, metrics, packet_id=7001):
    url = reverse("meshtastic-packet-ingest", kwargs={"node_id": feeder["node"].meshtastic_node_id})
    body = {
        "id": packet_id,
        "from": NODE,
        "to": 0xFFFFFFFF,
        "decoded": {"portnum": "TELEMETRY_APP", "telemetry": {"time": RX, variant: metrics}},
        "rxTime": RX,
    }
    return feeder["client"].post(url, body, format="json")


@pytest.mark.django_db
def test_environment_2_8_fields_round_trip(feeder):
    resp = _ingest(feeder, "environmentMetrics", {"temperature": 20.5, **ENV_KEYS})
    assert resp.status_code == 201, resp.content
    for row in (EnvironmentMetricsPacket.objects.get(), EnvironmentMetrics.objects.get()):
        assert row.temperature == 20.5
        for field, value in ENV_FIELDS.items():
            assert getattr(row, field) == value, field


@pytest.mark.django_db
def test_air_quality_2_8_pm_status_flags_round_trip(feeder):
    resp = _ingest(feeder, "airQualityMetrics", {"pm25Standard": 7, "pmStatusFlags": PM_STATUS_FLAGS})
    assert resp.status_code == 201, resp.content
    for row in (AirQualityMetricsPacket.objects.get(), AirQualityMetrics.objects.get()):
        assert row.pm25_standard == 7
        assert row.pm_status_flags == PM_STATUS_FLAGS


@pytest.mark.django_db
def test_2_7_shaped_packets_leave_new_fields_null(feeder):
    assert _ingest(feeder, "environmentMetrics", {"temperature": 20.5, "soilTemperature": 9.0}).status_code == 201
    assert _ingest(feeder, "airQualityMetrics", {"pm25Standard": 7}, packet_id=7002).status_code == 201
    for row in (EnvironmentMetricsPacket.objects.get(), EnvironmentMetrics.objects.get()):
        assert row.soil_temperature == 9.0
        assert all(getattr(row, field) is None for field in ENV_FIELDS)
    for row in (AirQualityMetricsPacket.objects.get(), AirQualityMetrics.objects.get()):
        assert row.pm_status_flags is None


@pytest.mark.django_db
def test_soil_water_variant_still_lands_in_generic_packet(feeder):
    resp = _ingest(feeder, "soilWaterMetrics", {"moisture": 4})
    assert resp.status_code == 201, resp.content
    assert GenericPacket.objects.get().telemetry_variant == "soilWaterMetrics"
    assert EnvironmentMetricsPacket.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "variant,key",
    [("environmentMetrics", "lightningStrikeCount1h"), ("airQualityMetrics", "pmStatusFlags")],
)
def test_negative_uint32_is_400_for_that_packet_only(feeder, variant, key):
    bad = _ingest(feeder, variant, {key: -1}, packet_id=7003)
    assert bad.status_code == 400
    assert EnvironmentMetricsPacket.objects.count() == 0
    assert AirQualityMetricsPacket.objects.count() == 0
    good = _ingest(feeder, variant, {key: 1}, packet_id=7004)
    assert good.status_code == 201, good.content
