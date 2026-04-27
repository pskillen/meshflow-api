"""HTTP API for DX notification subscription preferences (authenticated self-service)."""

from __future__ import annotations

from django.db import transaction

from rest_framework import permissions, status, views
from rest_framework.response import Response

from dx_monitoring.models import (
    DxNotificationCategorySelection,
    DxNotificationSubscription,
)
from dx_monitoring.serializers import (
    DxNotificationSettingsResponseSerializer,
    DxNotificationSettingsWriteSerializer,
    _available_dx_notification_category_values,
)
from users.discord_sync import user_has_verified_discord_dm_target

_ALL = _available_dx_notification_category_values()


def _discord_readiness_dict(user) -> dict:
    if user_has_verified_discord_dm_target(user):
        return {"status": "verified", "can_receive_dms": True}
    if not (getattr(user, "discord_notify_user_id", "") or "").strip():
        return {"status": "not_linked", "can_receive_dms": False}
    return {"status": "needs_relink", "can_receive_dms": False}


def _subscription_to_response(sub: DxNotificationSubscription) -> dict:
    if sub.all_categories:
        categories = list(_ALL)
    else:
        categories = list(sub.category_selections.values_list("category", flat=True).order_by("category"))
    return {
        "enabled": sub.enabled,
        "all_categories": sub.all_categories,
        "categories": categories,
        "discord": _discord_readiness_dict(sub.user),
    }


def _get_or_create_subscription(user) -> DxNotificationSubscription:
    sub, _ = DxNotificationSubscription.objects.get_or_create(
        user=user,
        defaults={
            "enabled": False,
            "all_categories": True,
        },
    )
    return sub


def _set_category_rows(sub: DxNotificationSubscription, categories: list[str]) -> None:
    with transaction.atomic():
        sub.category_selections.all().delete()
        for cat in categories:
            DxNotificationCategorySelection.objects.create(subscription=sub, category=cat)


def _current_categories_from_sub(sub: DxNotificationSubscription) -> list[str]:
    if sub.all_categories:
        return list(_ALL)
    return list(sub.category_selections.values_list("category", flat=True).order_by("category"))


class DxNotificationSettingsView(views.APIView):
    """
    Get or update the current user's DX notification preferences.

    GET, PUT, PATCH /api/dx/notifications/settings/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        sub = _get_or_create_subscription(request.user)
        return Response(DxNotificationSettingsResponseSerializer(instance=_subscription_to_response(sub)).data)

    def put(self, request):
        wser = DxNotificationSettingsWriteSerializer(
            data={
                "enabled": request.data.get("enabled", False),
                "all_categories": request.data.get("all_categories", True),
                "categories": request.data.get("categories", []),
            }
        )
        wser.is_valid(raise_exception=True)
        return self._apply_and_respond(request, wser.validated_data)

    def patch(self, request):
        sub = _get_or_create_subscription(request.user)
        merged = {
            "enabled": request.data.get("enabled", sub.enabled) if "enabled" in request.data else sub.enabled,
            "all_categories": (
                request.data.get("all_categories", sub.all_categories)
                if "all_categories" in request.data
                else sub.all_categories
            ),
            "categories": (
                request.data.get("categories", _current_categories_from_sub(sub))
                if "categories" in request.data
                else _current_categories_from_sub(sub)
            ),
        }
        wser = DxNotificationSettingsWriteSerializer(data=merged, partial=True)
        wser.is_valid(raise_exception=True)
        return self._apply_and_respond(request, wser.validated_data)

    def _apply_and_respond(self, request, vd: dict) -> Response:
        enabled = vd.get("enabled", False)
        all_cats = vd.get("all_categories", True)
        categories = list(vd.get("categories", []))
        if enabled and not user_has_verified_discord_dm_target(request.user):
            return Response(
                {
                    "code": "NEEDS_DISCORD_VERIFICATION",
                    "detail": (
                        "Connect Discord in your profile and keep notification settings verified "
                        "to enable Meshflow DMs. Use the Discord resync on the user settings page if needed."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        sub = _get_or_create_subscription(request.user)
        with transaction.atomic():
            sub.enabled = enabled
            sub.all_categories = all_cats
            if all_cats:
                sub.category_selections.all().delete()
            else:
                _set_category_rows(sub, categories)
            sub.save()
        sub.refresh_from_db()
        return Response(
            DxNotificationSettingsResponseSerializer(instance=_subscription_to_response(sub)).data,
            status=status.HTTP_200_OK,
        )
