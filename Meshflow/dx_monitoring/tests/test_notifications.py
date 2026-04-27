"""Tests for DX Discord notification subscription API and delivery."""

from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

import pytest
from allauth.socialaccount.models import SocialAccount
from rest_framework import status
from rest_framework.test import APIClient

import constellations.tests.conftest  # noqa: F401
import nodes.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from dx_monitoring.models import (
    DxEvent,
    DxEventState,
    DxNotificationCategory,
    DxNotificationDelivery,
    DxNotificationSubscription,
    DxReasonCode,
)
from dx_monitoring.notification_service import build_dx_discord_message, run_notify_dx_event
from push_notifications.constants import (
    DiscordNotificationFeature,
    DiscordNotificationKind,
    DiscordNotificationStatus,
)
from push_notifications.models import DiscordNotificationAudit
from users.discord_sync import sync_discord_notify_from_social_accounts


def _make_verified_discord_user(create_user, uid: str = "123456789012345678"):
    user = create_user()
    SocialAccount.objects.create(user=user, provider="discord", uid=uid, extra_data={})
    assert sync_discord_notify_from_social_accounts(user) is True
    user.refresh_from_db()
    return user


def _url():
    return reverse("dx-notifications-settings")


@pytest.mark.django_db
@override_settings(DX_MONITORING_NOTIFICATIONS_ENABLED=True)
def test_notification_settings_get_defaults(create_user):
    user = create_user()
    c = APIClient()
    c.force_authenticate(user=user)
    r = c.get(_url())
    assert r.status_code == status.HTTP_200_OK
    assert r.data["enabled"] is False
    assert r.data["all_categories"] is True
    assert "discord" in r.data
    assert r.data["discord"]["status"] in ("not_linked", "needs_relink", "verified")


@pytest.mark.django_db
@override_settings(DX_MONITORING_NOTIFICATIONS_ENABLED=True)
def test_notification_put_all_categories_false_requires_list(create_user):
    user = _make_verified_discord_user(create_user)
    c = APIClient()
    c.force_authenticate(user=user)
    r = c.put(
        _url(),
        {"enabled": True, "all_categories": False, "categories": []},
        format="json",
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert "categories" in r.data


@pytest.mark.django_db
def test_build_dx_message_respects_discord_length_limit(
    create_constellation,
    create_observed_node,
):
    c = create_constellation()
    dest = create_observed_node()
    now = timezone.now()
    long_meta = "x" * 5000
    dest.long_name = long_meta
    dest.save(update_fields=["long_name"])
    event = DxEvent.objects.create(
        constellation=c,
        destination=dest,
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
        observation_count=1,
    )
    text = build_dx_discord_message(
        event=event,
        category=DxNotificationCategory.NEW_DISTANT_NODE,
    )
    assert len(text) <= 2000


@pytest.mark.django_db
def test_notification_enable_requires_verified_discord(create_user):
    user = create_user()
    c = APIClient()
    c.force_authenticate(user=user)
    r = c.put(
        _url(),
        {"enabled": True, "all_categories": True, "categories": []},
        format="json",
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert r.data["code"] == "NEEDS_DISCORD_VERIFICATION"


@pytest.mark.django_db
@override_settings(DX_MONITORING_NOTIFICATIONS_ENABLED=True)
def test_notification_put_verified_user_ok(create_user):
    user = _make_verified_discord_user(create_user)
    c = APIClient()
    c.force_authenticate(user=user)
    r = c.put(
        _url(),
        {
            "enabled": True,
            "all_categories": True,
            "categories": [],
        },
        format="json",
    )
    assert r.status_code == status.HTTP_200_OK
    assert r.data["enabled"] is True
    assert r.data["discord"]["status"] == "verified"
    sub = DxNotificationSubscription.objects.get(user=user)
    assert sub.enabled is True
    assert sub.all_categories is True
    assert sub.category_selections.count() == 0


@pytest.mark.django_db
@override_settings(DX_MONITORING_NOTIFICATIONS_ENABLED=True)
def test_notification_put_granular_categories(create_user):
    user = _make_verified_discord_user(create_user)
    c = APIClient()
    c.force_authenticate(user=user)
    r = c.put(
        _url(),
        {
            "enabled": True,
            "all_categories": False,
            "categories": [DxNotificationCategory.NEW_DISTANT_NODE],
        },
        format="json",
    )
    assert r.status_code == status.HTTP_200_OK
    sub = DxNotificationSubscription.objects.get(user=user)
    assert not sub.all_categories
    assert set(sub.category_selections.values_list("category", flat=True)) == {DxNotificationCategory.NEW_DISTANT_NODE}


@pytest.mark.django_db
@override_settings(DX_MONITORING_NOTIFICATIONS_ENABLED=True, DISCORD_BOT_TOKEN="fake")
@patch("push_notifications.discord_audit.send_dm", autospec=True)
def test_notify_sends_to_subscriber_and_creates_delivery_and_audit(
    send_dm,
    create_user,
    create_constellation,
    create_observed_node,
):
    user = _make_verified_discord_user(create_user, uid="555000111222333444")
    DxNotificationSubscription.objects.get_or_create(
        user=user,
        defaults={"enabled": True, "all_categories": True},
    )[0].save()

    c = create_constellation()
    dest = create_observed_node(node_id=0xAABB00CC)
    now = timezone.now()
    event = DxEvent.objects.create(
        constellation=c,
        destination=dest,
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
        observation_count=1,
    )
    run_notify_dx_event(str(event.id), DxNotificationCategory.NEW_DISTANT_NODE)
    assert send_dm.call_count == 1
    assert DxNotificationDelivery.objects.filter(
        user=user, event=event, category=DxNotificationCategory.NEW_DISTANT_NODE
    ).exists()
    a = DiscordNotificationAudit.objects.filter(
        user=user,
        feature=DiscordNotificationFeature.DX_MONITORING,
        kind=DiscordNotificationKind.DX_NEW_DISTANT_NODE,
        status=DiscordNotificationStatus.SENT,
    )
    assert a.count() == 1


@pytest.mark.django_db
@override_settings(DX_MONITORING_NOTIFICATIONS_ENABLED=True)
def test_notify_unverified_creates_skipped_audit_only(
    create_user,
    create_constellation,
    create_observed_node,
):
    user = create_user()
    user.discord_notify_user_id = "999"
    user.save(update_fields=["discord_notify_user_id"])
    DxNotificationSubscription.objects.get_or_create(
        user=user,
        defaults={"enabled": True, "all_categories": True},
    )[0].save()

    c = create_constellation()
    dest = create_observed_node()
    now = timezone.now()
    event = DxEvent.objects.create(
        constellation=c,
        destination=dest,
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
        observation_count=1,
    )
    run_notify_dx_event(str(event.id), DxNotificationCategory.NEW_DISTANT_NODE)
    assert not DxNotificationDelivery.objects.filter(user=user, event=event).exists()
    a = DiscordNotificationAudit.objects.filter(
        user=user,
        status=DiscordNotificationStatus.SKIPPED,
    )
    assert a.count() == 1
    assert "not verified" in a.first().reason.lower()


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_NOTIFICATIONS_ENABLED=True,
    DX_MONITORING_NOTIFICATION_CATEGORY_COOLDOWN_MINUTES=0,
    DISCORD_BOT_TOKEN="fake",
)
@patch("push_notifications.discord_audit.send_dm", autospec=True)
def test_idempotent_no_second_delivery_or_send(
    send_dm,
    create_user,
    create_constellation,
    create_observed_node,
):
    user = _make_verified_discord_user(create_user)
    DxNotificationSubscription.objects.get_or_create(
        user=user,
        defaults={"enabled": True, "all_categories": True},
    )[0].save()
    c = create_constellation()
    dest = create_observed_node()
    now = timezone.now()
    event = DxEvent.objects.create(
        constellation=c,
        destination=dest,
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
        observation_count=1,
    )
    run_notify_dx_event(str(event.id), DxNotificationCategory.NEW_DISTANT_NODE)
    assert send_dm.call_count == 1
    run_notify_dx_event(str(event.id), DxNotificationCategory.NEW_DISTANT_NODE)
    assert send_dm.call_count == 1


@pytest.mark.django_db
@override_settings(
    DX_MONITORING_NOTIFICATIONS_ENABLED=True,
    DX_MONITORING_NOTIFICATION_CATEGORY_COOLDOWN_MINUTES=60,
    DISCORD_BOT_TOKEN="fake",
)
@patch("push_notifications.discord_audit.send_dm", autospec=True)
def test_category_cooldown_skips_second_event(
    send_dm,
    create_user,
    create_constellation,
    create_observed_node,
):
    user = _make_verified_discord_user(create_user)
    DxNotificationSubscription.objects.get_or_create(
        user=user,
        defaults={"enabled": True, "all_categories": True},
    )[0].save()
    const = create_constellation()
    dest1 = create_observed_node()
    now = timezone.now()
    e1 = DxEvent.objects.create(
        constellation=const,
        destination=dest1,
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
        observation_count=1,
    )
    e2 = DxEvent.objects.create(
        constellation=const,
        destination=create_observed_node(node_id=0xDEAD00BE),
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
        observation_count=1,
    )
    run_notify_dx_event(str(e1.id), DxNotificationCategory.NEW_DISTANT_NODE)
    run_notify_dx_event(str(e2.id), DxNotificationCategory.NEW_DISTANT_NODE)
    assert send_dm.call_count == 1
    skips = DiscordNotificationAudit.objects.filter(
        user=user,
        status=DiscordNotificationStatus.SKIPPED,
    )
    assert "cool-down" in skips.last().reason.lower() or "cool" in skips.last().reason.lower()


@pytest.mark.django_db
@override_settings(DX_MONITORING_NOTIFICATIONS_ENABLED=True, DISCORD_BOT_TOKEN="fake")
@patch("push_notifications.discord_audit.send_dm", autospec=True)
def test_send_failure_creates_failed_audit(
    send_dm,
    create_user,
    create_constellation,
    create_observed_node,
):
    from push_notifications.discord import DiscordSendError

    send_dm.side_effect = DiscordSendError("test failure")
    user = _make_verified_discord_user(create_user)
    DxNotificationSubscription.objects.get_or_create(
        user=user,
        defaults={"enabled": True, "all_categories": True},
    )[0].save()
    c = create_constellation()
    dest = create_observed_node()
    now = timezone.now()
    event = DxEvent.objects.create(
        constellation=c,
        destination=dest,
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
        observation_count=1,
    )
    run_notify_dx_event(str(event.id), DxNotificationCategory.NEW_DISTANT_NODE)
    assert not DxNotificationDelivery.objects.filter(user=user, event=event).exists()
    a = DiscordNotificationAudit.objects.get(
        user=user,
        status=DiscordNotificationStatus.FAILED,
    )
    assert "test failure" in a.reason
