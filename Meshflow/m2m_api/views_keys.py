"""JWT key management and staff withdraw. Not part of the public M2M contract."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.access import user_can_mint_m2m_keys
from common.drf_permissions import IsSystemAdmin

from .models import M2MApiKey, M2MApiKeyUsageDaily
from .services import withdraw_m2m_access
from .terms import TERMS_TEXT

User = get_user_model()


def _usage_counts(key):
    today = timezone.now().date()
    start = today - timedelta(days=29)
    rows = M2MApiKeyUsageDaily.objects.filter(key=key, date__gte=start)
    today_count = 0
    total = 0
    for row in rows:
        total += row.request_count
        if row.date == today:
            today_count = row.request_count
    return today_count, total


def _key_payload(key, *, raw=None):
    requests_today, requests_30d = _usage_counts(key)
    payload = {
        "id": str(key.id),
        "name": key.name,
        "prefix": key.prefix,
        "intended_use": key.intended_use,
        "created_at": key.created_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
        "revoked_reason": key.revoked_reason,
        "terms_version": key.terms_version,
        "terms_accepted_at": key.terms_accepted_at,
        "terms_action_required": key.terms_action_required(),
        "rate_tier": key.rate_tier,
        "requests_today": requests_today,
        "requests_30d": requests_30d,
    }
    if raw:
        payload["key"] = raw
    return payload


class TermsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "version": settings.M2M_TERMS_VERSION,
                "grace_days": settings.M2M_TERMS_GRACE_DAYS,
                "licence": "CC BY-NC 4.0",
                "text": TERMS_TEXT,
            }
        )


class KeyListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_can_mint_m2m_keys(request.user) and not M2MApiKey.objects.filter(owner=request.user).exists():
            return Response({"detail": "M2M API access has not been granted."}, status=status.HTTP_403_FORBIDDEN)
        keys = M2MApiKey.objects.filter(owner=request.user).order_by("-created_at")
        return Response([_key_payload(key) for key in keys])

    def post(self, request):
        if not user_can_mint_m2m_keys(request.user):
            return Response({"detail": "M2M API access has not been granted."}, status=status.HTTP_403_FORBIDDEN)
        if not request.data.get("accept_terms"):
            return Response({"detail": "Current terms must be accepted."}, status=status.HTTP_400_BAD_REQUEST)
        name = (request.data.get("name") or "").strip()
        intended = (request.data.get("intended_use") or "").strip()
        if not name or not intended:
            return Response({"detail": "name and intended_use are required."}, status=status.HTTP_400_BAD_REQUEST)
        active = M2MApiKey.objects.filter(owner=request.user, revoked_at__isnull=True).count()
        if active >= settings.M2M_KEY_CAP:
            return Response({"detail": "Key cap reached."}, status=status.HTTP_400_BAD_REQUEST)
        key, raw = M2MApiKey.mint(owner=request.user, name=name, intended_use=intended)
        return Response(_key_payload(key, raw=raw), status=status.HTTP_201_CREATED)


class KeyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, key_id):
        key = get_object_or_404(M2MApiKey, id=key_id, owner=request.user)
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "name is required."}, status=status.HTTP_400_BAD_REQUEST)
        key.name = name
        key.save(update_fields=["name"])
        return Response(_key_payload(key))


class KeyRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, key_id):
        key = get_object_or_404(M2MApiKey, id=key_id, owner=request.user)
        if key.revoked_at is None:
            key.revoked_at = timezone.now()
            key.revoked_reason = "owner_revoked"
            key.save(update_fields=["revoked_at", "revoked_reason"])
        return Response(_key_payload(key))


class KeyAcceptTermsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, key_id):
        key = get_object_or_404(M2MApiKey, id=key_id, owner=request.user)
        if key.revoked_at is not None:
            return Response({"detail": "Key is revoked."}, status=status.HTTP_400_BAD_REQUEST)
        key.terms_version = settings.M2M_TERMS_VERSION
        key.terms_accepted_at = timezone.now()
        key.save(update_fields=["terms_version", "terms_accepted_at"])
        return Response(_key_payload(key))


class WithdrawView(APIView):
    permission_classes = [IsSystemAdmin]

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        return Response(withdraw_m2m_access(user, by=request.user))
