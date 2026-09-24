"""DRF throttles for guest-readable views and the M2M API.

Throttles are attached per view. They are not ``DEFAULT_THROTTLE_CLASSES``, so
packet ingest and WebSockets are not covered.
"""

import logging

from django.conf import settings

from rest_framework.exceptions import Throttled
from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def client_ip(request) -> str:
    """Client address for rate-limit buckets.

    ``CF-Connecting-IP`` is trusted only when ``TRUST_CF_CONNECTING_IP`` is set
    (production, behind Cloudflare Tunnel). Otherwise ``REMOTE_ADDR``.
    """
    if getattr(settings, "TRUST_CF_CONNECTING_IP", False):
        cf_ip = (request.META.get("HTTP_CF_CONNECTING_IP") or "").strip()
        if cf_ip:
            return cf_ip.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "unknown").strip() or "unknown"


def _is_authenticated(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated)


class _GuestIpThrottle(SimpleRateThrottle):
    """Count only anonymous requests, keyed on :func:`client_ip`."""

    def get_cache_key(self, request, view):
        if _is_authenticated(request):
            return None
        return self.cache_format % {"scope": self.scope, "ident": client_ip(request)}


class GuestBurstThrottle(_GuestIpThrottle):
    scope = "guest_burst"


class GuestExpensiveThrottle(_GuestIpThrottle):
    scope = "guest_expensive"


class MeshflowUserRateThrottle(UserRateThrottle):
    """Backstop for authenticated JWT users. Anonymous requests are not counted."""

    scope = "user"


GUEST_READ_THROTTLE_CLASSES = [GuestBurstThrottle, MeshflowUserRateThrottle]
GUEST_EXPENSIVE_THROTTLE_CLASSES = [
    GuestBurstThrottle,
    GuestExpensiveThrottle,
    MeshflowUserRateThrottle,
]


def guest_read_throttles(*, expensive: bool = False):
    classes = GUEST_EXPENSIVE_THROTTLE_CLASSES if expensive else GUEST_READ_THROTTLE_CLASSES
    return [cls() for cls in classes]


def meshflow_exception_handler(exc, context):
    """DRF handler that logs 429s (Retry-After is already set by DRF)."""
    if isinstance(exc, Throttled):
        request = context.get("request")
        logger.warning(
            "HTTP 429 throttle path=%s wait=%s",
            getattr(request, "path", ""),
            exc.wait,
        )
    return exception_handler(exc, context)
