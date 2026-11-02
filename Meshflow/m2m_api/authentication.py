"""M2M key authentication. JWT and NodeAPIKey are not accepted on these routes."""

from datetime import timedelta

from django.utils import timezone

from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication

from m2m_api.models import M2MApiKey


class M2MApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        raw = (request.META.get("HTTP_X_API_KEY") or "").strip()
        if not raw:
            header = request.META.get("HTTP_AUTHORIZATION") or ""
            if header.startswith("Bearer mfk_"):
                raw = header[len("Bearer ") :].strip()
            else:
                raise exceptions.AuthenticationFailed("M2M API key required (X-API-KEY or Bearer mfk_…)")
        if not raw.startswith("mfk_") or raw.count("_") < 2:
            raise exceptions.AuthenticationFailed("Invalid API key")
        prefix = raw.split("_", 2)[1]
        try:
            key = M2MApiKey.objects.select_related("owner").get(prefix=prefix)
        except M2MApiKey.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid API key")
        if not key.matches(raw):
            raise exceptions.AuthenticationFailed("Invalid API key")
        if key.revoked_at is not None or not key.owner.is_active:
            raise exceptions.AuthenticationFailed("Invalid API key")
        if key.terms_expired():
            raise exceptions.PermissionDenied("Terms of use must be re-accepted")
        request.m2m_terms_action_required = key.terms_action_required()
        self._touch_last_used(key)
        return (key.owner, key)

    def authenticate_header(self, request):
        return "X-API-KEY"

    @staticmethod
    def _touch_last_used(key):
        now = timezone.now()
        if key.last_used_at and now - key.last_used_at < timedelta(minutes=5):
            return
        key.last_used_at = now
        key.save(update_fields=["last_used_at"])
