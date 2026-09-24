"""Redis daily counters, flushed hourly into Postgres."""

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from prometheus_client import Counter

from .models import M2MApiKeyUsageDaily

M2M_REQUESTS = Counter("meshflow_m2m_requests_total", "Authenticated M2M requests", ["endpoint"])


def record_m2m_request(key, path: str):
    day = timezone.now().date().isoformat()
    cache_key = f"m2m:usage:{key.id}:{day}"
    try:
        cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=int(timedelta(days=3).total_seconds()))
    try:
        M2M_REQUESTS.labels(endpoint=path).inc()
    except Exception:
        pass


def flush_m2m_usage():
    """Upsert Redis counters into M2MApiKeyUsageDaily. Safe to run more than once an hour."""
    from .models import M2MApiKey

    today = timezone.now().date()
    days = [today - timedelta(days=offset) for offset in range(3)]
    for key in M2MApiKey.objects.all().only("id"):
        for day in days:
            cache_key = f"m2m:usage:{key.id}:{day.isoformat()}"
            raw = cache.get(cache_key)
            if not raw:
                continue
            row, _created = M2MApiKeyUsageDaily.objects.get_or_create(key=key, date=day, defaults={"request_count": 0})
            count = int(raw)
            if row.request_count != count:
                row.request_count = count
                row.save(update_fields=["request_count"])
