"""Guest throttle behaviour."""

from datetime import datetime, timedelta, timezone

from django.core.cache import cache
from django.test import RequestFactory, override_settings

import pytest
from rest_framework.test import APIClient

from common.throttling import client_ip
from packets.views import PacketIngestView
from stats.views import _clamp_guest_stats_range

pytestmark = pytest.mark.django_db

LOW_RATES = {
    "guest_burst": "2/min",
    "guest_expensive": "1/min",
    "user": "5/min",
    "m2m_key_min": "60/min",
    "m2m_key_day": "5000/day",
    "m2m_owner_min": "60/min",
    "m2m_owner_day": "5000/day",
}


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_client_ip_ignores_cf_header_unless_enabled():
    request = RequestFactory().get("/", HTTP_CF_CONNECTING_IP="203.0.113.5", REMOTE_ADDR="10.0.0.1")
    assert client_ip(request) == "10.0.0.1"
    with override_settings(TRUST_CF_CONNECTING_IP=True):
        assert client_ip(request) == "203.0.113.5"


@pytest.fixture
def low_guest_rates():
    from common.throttling import GuestBurstThrottle, GuestExpensiveThrottle, MeshflowUserRateThrottle

    classes = (GuestBurstThrottle, GuestExpensiveThrottle, MeshflowUserRateThrottle)
    saved = [(cls, cls.THROTTLE_RATES) for cls in classes]
    rates = {**GuestBurstThrottle.THROTTLE_RATES, **LOW_RATES}
    for cls in classes:
        cls.THROTTLE_RATES = rates
    yield
    for cls, old in saved:
        cls.THROTTLE_RATES = old


def test_guest_burst_returns_429_with_retry_after(low_guest_rates):
    client = APIClient()
    statuses = [client.get("/api/constellations/").status_code for _ in range(3)]
    assert statuses[:2] == [200, 200]
    assert statuses[2] == 429
    assert "Retry-After" in client.get("/api/constellations/").headers


def test_authenticated_user_is_not_on_the_guest_bucket(create_user, low_guest_rates):
    guest = APIClient()
    assert guest.get("/api/constellations/").status_code == 200
    assert guest.get("/api/constellations/").status_code == 200
    assert guest.get("/api/constellations/").status_code == 429

    user = create_user()
    authed = APIClient()
    authed.force_authenticate(user=user)
    assert authed.get("/api/constellations/").status_code == 200


def test_ingest_views_have_no_throttles():
    assert PacketIngestView.throttle_classes == []


def test_guest_stats_global_clamps_open_range():
    class _Req:
        class user:
            is_authenticated = False

        pass

    start, end = _clamp_guest_stats_range(_Req(), None, None)
    assert end - start == timedelta(days=30)

    far = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 9, 1, tzinfo=timezone.utc)
    start, clamped_end = _clamp_guest_stats_range(_Req(), far, end)
    assert clamped_end == end
    assert clamped_end - start == timedelta(days=30)
