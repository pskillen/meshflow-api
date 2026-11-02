import math
from datetime import timedelta
from itertools import count

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework.test import APIClient

from common.geo import haversine_km
from nodes.models import NodeLatestStatus, RoleSource
from nodes.services import nearby_infrastructure as svc

CENTRE_LAT, CENTRE_LON = 55.86, -4.25
KM_PER_DEG_LAT = 111.32
CONTRACT_FIELDS = [
    "internal_id",
    "node_id_str",
    "long_name",
    "short_name",
    "meshtastic_role",
    "meshtastic_role_label",
    "meshtastic_hw_model",
    "last_heard",
    "latitude",
    "longitude",
    "altitude",
    "distance_km",
]
_ids = count(0x20000000)


@pytest.fixture(autouse=True)
def _clear_cache_and_disable(settings):
    cache.clear()
    settings.NEARBY_INFRASTRUCTURE_CACHE_SECONDS = 0
    yield
    cache.clear()


@pytest.fixture
def url():
    return reverse("observed-node-infrastructure-nearby")


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def infra(create_observed_node):
    def _infra(
        meshtastic_node_id=None,
        role=RoleSource.ROUTER,
        lat=CENTRE_LAT + 0.027,
        lon=CENTRE_LON,
        heard_days_ago=1,
        altitude=100.0,
        with_position=True,
        **kw,
    ):
        node = create_observed_node(
            meshtastic_node_id=meshtastic_node_id if meshtastic_node_id is not None else next(_ids),
            meshtastic_role=role,
            last_heard=(timezone.now() - timedelta(days=heard_days_ago)) if heard_days_ago is not None else None,
            **kw,
        )
        if with_position:
            NodeLatestStatus.objects.create(node=node, latitude=lat, longitude=lon, altitude=altitude)
        return node

    return _infra


def _get(client, url, **params):
    base = {"lat": CENTRE_LAT, "lon": CENTRE_LON}
    base.update(params)
    return client.get(url, {k: v for k, v in base.items() if v is not None})


def _ids_of(resp):
    return [r["node_id_str"] for r in resp.json()["results"]]


@pytest.mark.django_db
def test_anonymous_get_returns_200_with_contract_shape(client, url, infra):
    assert url == "/api/nodes/observed-nodes/infrastructure/nearby/"
    lat = CENTRE_LAT + 0.027
    infra(lat=lat)
    resp = _get(client, url)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"results", "meta"}
    assert len(body["results"]) == 1
    row = body["results"][0]
    assert list(row.keys()) == CONTRACT_FIELDS
    assert row["meshtastic_role_label"] == "ROUTER"
    assert row["distance_km"] == pytest.approx(haversine_km(CENTRE_LAT, CENTRE_LON, lat, CENTRE_LON), abs=0.1)
    assert body["meta"] == {
        "lat": 55.86,
        "lon": -4.25,
        "radius_km": 25.0,
        "last_heard_within_days": 30,
        "count": 1,
        "truncated": False,
    }
    assert list(body["meta"].keys()) == [
        "lat",
        "lon",
        "radius_km",
        "last_heard_within_days",
        "count",
        "truncated",
    ]


@pytest.mark.django_db
def test_invalid_bearer_token_does_not_401(client, url, infra):
    infra()
    resp = client.get(url, {"lat": CENTRE_LAT, "lon": CENTRE_LON}, HTTP_AUTHORIZATION="Bearer not-a-real-token")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_cors_star_for_foreign_origin(client, url):
    resp = client.get(url, {"lat": 1, "lon": 1}, HTTP_ORIGIN="https://codeplug.example")
    assert resp["Access-Control-Allow-Origin"] == "*"
    assert "Access-Control-Allow-Credentials" not in resp


@pytest.mark.django_db
def test_cors_star_without_origin_header(client, url):
    resp = client.get(url, {"lat": 1, "lon": 1})
    assert resp["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_cors_on_400_response(client, url):
    resp = client.get(url, {"lon": 1}, HTTP_ORIGIN="https://codeplug.example")
    assert resp.status_code == 400
    assert resp["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_allowed_origin_gets_echoed_origin(client, url, settings):
    settings.CORS_ALLOWED_ORIGINS = ["https://meshflow.example"]
    resp = client.get(url, {"lat": 1, "lon": 1}, HTTP_ORIGIN="https://meshflow.example")
    assert resp["Access-Control-Allow-Origin"] == "https://meshflow.example"


@pytest.mark.django_db
def test_other_endpoints_do_not_get_cors_star(client):
    resp = client.get("/api/nodes/observed-nodes/", HTTP_ORIGIN="https://codeplug.example")
    assert "Access-Control-Allow-Origin" not in resp


@pytest.mark.django_db
def test_only_infrastructure_roles_included(client, url, infra):
    included = {
        infra(role=r).meshtastic_node_id for r in (RoleSource.ROUTER, RoleSource.ROUTER_CLIENT, RoleSource.REPEATER)
    }
    included.add(infra(role=RoleSource.ROUTER_LATE).meshtastic_node_id)
    for r in (RoleSource.CLIENT, RoleSource.CLIENT_MUTE, RoleSource.TRACKER, RoleSource.CLIENT_BASE, None):
        infra(role=r)
    resp = _get(client, url)
    got = {int(i[1:], 16) for i in _ids_of(resp)}
    assert got == included


@pytest.mark.django_db
def test_include_client_base_true_includes_client_base(client, url, infra):
    base = infra(role=RoleSource.CLIENT_BASE)
    infra(role=RoleSource.CLIENT)
    on = _ids_of(_get(client, url, include_client_base="true"))
    assert on == [f"!{base.meshtastic_node_id:08x}"]
    assert _ids_of(_get(client, url, include_client_base="false")) == []
    assert _ids_of(_get(client, url)) == []


@pytest.mark.django_db
def test_client_positions_never_leak(client, url, infra):
    node = infra(role=RoleSource.CLIENT, lat=55.861234, lon=-4.251234)
    resp = _get(client, url, include_client_base="true")
    raw = resp.content.decode()
    assert str(node.internal_id) not in raw
    assert f"{node.meshtastic_node_id:08x}" not in raw
    assert "55.861234" not in raw
    assert "-4.251234" not in raw


@pytest.mark.django_db
def test_meshcore_nodes_excluded(client, url, create_observed_node):
    mc = create_observed_node(protocol=2, meshtastic_role=None, last_heard=timezone.now())
    NodeLatestStatus.objects.create(node=mc, latitude=CENTRE_LAT, longitude=CENTRE_LON)
    resp = _get(client, url, include_client_base="true")
    assert resp.json()["results"] == []


@pytest.mark.django_db
def test_nodes_without_position_excluded(client, url, infra):
    infra(with_position=False)
    n = infra(with_position=False)
    NodeLatestStatus.objects.create(node=n, latitude=None, longitude=None)
    infra(lat=0.0, lon=0.0)
    assert _ids_of(_get(client, url)) == []
    assert _ids_of(_get(client, url, lat=0, lon=0)) == []


@pytest.mark.django_db
def test_never_heard_excluded(client, url, infra):
    infra(heard_days_ago=None)
    assert _ids_of(_get(client, url)) == []


@pytest.mark.django_db
def test_last_heard_window(client, url, infra):
    recent = infra(heard_days_ago=5)
    old = infra(heard_days_ago=40)
    assert _ids_of(_get(client, url)) == [f"!{recent.meshtastic_node_id:08x}"]
    assert set(_ids_of(_get(client, url, last_heard_within_days=60))) == {
        f"!{recent.meshtastic_node_id:08x}",
        f"!{old.meshtastic_node_id:08x}",
    }
    assert _ids_of(_get(client, url, last_heard_within_days=3)) == []


@pytest.mark.django_db
def test_radius_filter_exact_not_bbox(client, url, infra):
    a = infra(lat=CENTRE_LAT + 0.18)
    dlon = 20 / (KM_PER_DEG_LAT * math.cos(math.radians(CENTRE_LAT)))
    b = infra(lat=CENTRE_LAT + 0.18, lon=CENTRE_LON + dlon)
    a_id = f"!{a.meshtastic_node_id:08x}"
    b_id = f"!{b.meshtastic_node_id:08x}"
    assert _ids_of(_get(client, url)) == [a_id]
    assert set(_ids_of(_get(client, url, radius_km=30))) == {a_id, b_id}


@pytest.mark.django_db
def test_sorted_nearest_first(client, url, infra):
    far = infra(lat=CENTRE_LAT + 15 / KM_PER_DEG_LAT)
    near = infra(lat=CENTRE_LAT + 2 / KM_PER_DEG_LAT)
    mid = infra(lat=CENTRE_LAT + 8 / KM_PER_DEG_LAT)
    resp = _get(client, url)
    assert _ids_of(resp) == [f"!{n.meshtastic_node_id:08x}" for n in (near, mid, far)]
    dists = [r["distance_km"] for r in resp.json()["results"]]
    assert dists == sorted(dists)


@pytest.mark.django_db
def test_radius_clamped(client, url, infra):
    infra(lat=CENTRE_LAT + 150 / KM_PER_DEG_LAT)
    assert _get(client, url, radius_km=0.1).json()["meta"]["radius_km"] == 1.0
    resp = _get(client, url, radius_km=500)
    assert resp.json()["meta"]["radius_km"] == 100.0
    assert resp.json()["results"] == []


@pytest.mark.django_db
def test_days_clamped(client, url):
    assert _get(client, url, last_heard_within_days=0).json()["meta"]["last_heard_within_days"] == 1
    assert _get(client, url, last_heard_within_days=9999).json()["meta"]["last_heard_within_days"] == 365


@pytest.mark.django_db
@pytest.mark.parametrize(
    "params",
    [
        {"lat": None},
        {"lon": None},
        {"lat": "abc"},
        {"lat": "nan"},
        {"lon": "inf"},
        {"lat": 91},
        {"lat": -90.5},
        {"lon": 181},
        {"radius_km": "abc"},
        {"last_heard_within_days": "abc"},
    ],
)
def test_400s(client, url, params):
    resp = _get(client, url, **params)
    assert resp.status_code == 400
    assert isinstance(resp.json()["error"], str)


@pytest.mark.django_db
def test_lat_lon_rounded_in_meta(client, url):
    meta = _get(client, url, lat="55.861234", lon="-4.251234").json()["meta"]
    assert meta["lat"] == 55.861
    assert meta["lon"] == -4.251


@pytest.mark.django_db
def test_truncated_at_max_results(client, url, infra, monkeypatch):
    monkeypatch.setattr(svc, "MAX_RESULTS", 3)
    for _ in range(3):
        infra()
    meta = _get(client, url).json()["meta"]
    assert meta["count"] == 3
    assert meta["truncated"] is False
    infra()
    resp = _get(client, url)
    assert len(resp.json()["results"]) == 3
    assert resp.json()["meta"]["count"] == 3
    assert resp.json()["meta"]["truncated"] is True


@pytest.mark.django_db
def test_longitude_wrap_near_antimeridian(client, url, infra):
    east = infra(lat=0.0, lon=-179.95)
    resp = _get(client, url, lat=0, lon=179.9)
    assert _ids_of(resp) == [f"!{east.meshtastic_node_id:08x}"]
    assert resp.json()["results"][0]["distance_km"] < 20

    west = infra(lat=0.0, lon=179.95)
    resp = _get(client, url, lat=0, lon=-179.9)
    assert f"!{west.meshtastic_node_id:08x}" in _ids_of(resp)
    assert all(r["distance_km"] < 20 for r in resp.json()["results"])


@pytest.mark.django_db
def test_near_pole_does_not_crash(client, url, infra):
    node = infra(lat=89.9, lon=100.0)
    resp = _get(client, url, lat=89.95, lon=0)
    assert resp.status_code == 200
    assert _ids_of(resp) == [f"!{node.meshtastic_node_id:08x}"]


@pytest.mark.django_db
def test_response_cached_when_enabled(client, url, infra, settings):
    settings.NEARBY_INFRASTRUCTURE_CACHE_SECONDS = 60
    infra()
    first = _get(client, url)
    assert len(first.json()["results"]) == 1
    assert "max-age=60" in first["Cache-Control"]
    infra()
    assert len(_get(client, url).json()["results"]) == 1
    cache.clear()
    assert len(_get(client, url).json()["results"]) == 2


@pytest.mark.django_db
def test_cache_disabled_when_zero(client, url, infra):
    infra()
    assert len(_get(client, url).json()["results"]) == 1
    infra()
    resp = _get(client, url)
    assert len(resp.json()["results"]) == 2
    assert "max-age=0" in resp["Cache-Control"]


@pytest.mark.django_db
def test_post_not_allowed(client, url):
    assert client.post(url, {"lat": 1, "lon": 1}).status_code == 405


def test_parse_params_rounding_and_clamping():
    from django.http import QueryDict

    p = svc.parse_nearby_params(QueryDict("lat=10.12345&lon=-20.98765&radius_km=0.04&last_heard_within_days=400"))
    assert (p.lat, p.lon, p.radius_km, p.last_heard_within_days) == (10.123, -20.988, 1.0, 365)
    assert p.include_client_base is False


@pytest.mark.django_db
def test_guest_throttled_with_cors_on_429(client, url):
    from common.throttling import GuestBurstThrottle, MeshflowUserRateThrottle

    saved = [(cls, cls.THROTTLE_RATES) for cls in (GuestBurstThrottle, MeshflowUserRateThrottle)]
    rates = {**GuestBurstThrottle.THROTTLE_RATES, "guest_burst": "2/min"}
    for cls, _ in saved:
        cls.THROTTLE_RATES = rates
    try:
        params = {"lat": CENTRE_LAT, "lon": CENTRE_LON}
        responses = [client.get(url, params, HTTP_ORIGIN="https://example.org") for _ in range(3)]
    finally:
        for cls, old in saved:
            cls.THROTTLE_RATES = old
    assert [r.status_code for r in responses] == [200, 200, 429]
    assert responses[2]["Access-Control-Allow-Origin"] == "*"
    assert "Retry-After" in responses[2]
