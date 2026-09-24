"""Rate limits keyed on the M2M key and its owner."""

from rest_framework.throttling import SimpleRateThrottle

from m2m_api.models import M2MApiKey

_ELEVATED = {
    "m2m_key_min": "120/min",
    "m2m_key_day": "20000/day",
    "m2m_owner_min": "120/min",
    "m2m_owner_day": "20000/day",
}


class _M2MThrottle(SimpleRateThrottle):
    def allow_request(self, request, view):
        key = request.auth if isinstance(getattr(request, "auth", None), M2MApiKey) else None
        if key is not None and key.rate_tier == M2MApiKey.RateTier.ELEVATED:
            self.rate = _ELEVATED[self.scope]
            self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)


class M2MKeyMinThrottle(_M2MThrottle):
    scope = "m2m_key_min"

    def get_cache_key(self, request, view):
        key = request.auth if isinstance(getattr(request, "auth", None), M2MApiKey) else None
        if key is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(key.id)}


class M2MKeyDayThrottle(M2MKeyMinThrottle):
    scope = "m2m_key_day"


class M2MOwnerMinThrottle(_M2MThrottle):
    scope = "m2m_owner_min"

    def get_cache_key(self, request, view):
        key = request.auth if isinstance(getattr(request, "auth", None), M2MApiKey) else None
        if key is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": f"owner-{key.owner_id}"}


class M2MOwnerDayThrottle(M2MOwnerMinThrottle):
    scope = "m2m_owner_day"


M2M_THROTTLE_CLASSES = [M2MKeyMinThrottle, M2MKeyDayThrottle, M2MOwnerMinThrottle, M2MOwnerDayThrottle]
