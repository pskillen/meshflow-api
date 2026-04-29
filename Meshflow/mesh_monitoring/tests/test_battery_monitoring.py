"""Battery monitoring evaluation and alert summary API tests."""

from django.utils import timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient

import nodes.tests.conftest  # noqa: F401
from mesh_monitoring.battery import evaluate_device_metrics_for_battery_alert
from mesh_monitoring.models import NodeMonitoringConfig, NodePresence, NodeWatch
from nodes.constants import INFRASTRUCTURE_ROLES


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_battery_alert_confirms_after_n_low_reports(create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(claimed_by=user, role=INFRASTRUCTURE_ROLES[0])
    NodeWatch.objects.create(user=user, observed_node=obs, enabled=True, battery_notifications_enabled=True)
    NodeMonitoringConfig.objects.create(
        observed_node=obs,
        last_heard_offline_after_seconds=21600,
        battery_alert_enabled=True,
        battery_alert_threshold_percent=50,
        battery_alert_report_count=2,
    )
    evaluate_device_metrics_for_battery_alert(observed_node=obs, battery_level=40.0, reported_time=timezone.now())
    p = NodePresence.objects.get(pk=obs.pk)
    assert p.battery_below_threshold_report_count == 1
    assert p.battery_alert_confirmed_at is None

    evaluate_device_metrics_for_battery_alert(observed_node=obs, battery_level=30.0, reported_time=timezone.now())
    p.refresh_from_db()
    assert p.battery_below_threshold_report_count == 2
    assert p.battery_alert_confirmed_at is not None


@pytest.mark.django_db
def test_battery_recovery_clears_streak(create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(claimed_by=user)
    NodeMonitoringConfig.objects.create(
        observed_node=obs,
        battery_alert_enabled=True,
        battery_alert_threshold_percent=50,
        battery_alert_report_count=1,
    )
    NodePresence.objects.create(observed_node=obs, is_offline=False, battery_below_threshold_report_count=3)
    evaluate_device_metrics_for_battery_alert(observed_node=obs, battery_level=90.0, reported_time=timezone.now())
    p = NodePresence.objects.get(pk=obs.pk)
    assert p.battery_below_threshold_report_count == 0
    assert p.battery_alert_confirmed_at is None


@pytest.mark.django_db
def test_monitoring_alerts_summary_mesh_infra(api_client, create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(role=INFRASTRUCTURE_ROLES[0], claimed_by=None)
    NodePresence.objects.create(observed_node=obs, is_offline=True, offline_confirmed_at=timezone.now())

    api_client.force_authenticate(user=user)
    r = api_client.get("/api/monitoring/alerts/summary/?scope=mesh_infra")
    assert r.status_code == status.HTTP_200_OK
    assert r.data["mesh_infra"]["alerting_nodes_count"] >= 1
    assert r.data["mesh_infra"]["offline_count"] >= 1


@pytest.mark.django_db
def test_monitoring_alerts_summary_bad_scope(api_client, create_user):
    api_client.force_authenticate(user=create_user())
    r = api_client.get("/api/monitoring/alerts/summary/")
    assert r.status_code == status.HTTP_400_BAD_REQUEST
