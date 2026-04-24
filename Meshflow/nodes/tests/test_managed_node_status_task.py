"""Tests for ManagedNodeStatus refresh task."""

from datetime import timedelta

from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
from nodes.models import ManagedNodeStatus
from nodes.tasks import update_managed_node_statuses


@pytest.mark.django_db
def test_update_managed_node_statuses_creates_and_sets_sending(
    monkeypatch,
    create_managed_node,
    create_packet_observation,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    mn = create_managed_node()
    ManagedNodeStatus.objects.filter(node=mn).delete()

    create_packet_observation(observer=mn)

    result = update_managed_node_statuses()

    assert result["created"] >= 1
    assert result["sending"] >= 1
    st = ManagedNodeStatus.objects.get(node=mn)
    assert st.last_packet_ingested_at is not None
    assert st.is_sending_data is True


@pytest.mark.django_db
def test_update_managed_node_statuses_stale_observation_not_sending(
    monkeypatch,
    create_managed_node,
    create_packet_observation,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    mn = create_managed_node()
    ManagedNodeStatus.objects.filter(node=mn).delete()

    obs = create_packet_observation(observer=mn)
    obs.upload_time = timezone.now() - timedelta(seconds=700)
    obs.save(update_fields=["upload_time"])

    result = update_managed_node_statuses()

    assert result["sending"] == 0
    st = ManagedNodeStatus.objects.get(node=mn)
    assert st.is_sending_data is False


@pytest.mark.django_db
def test_update_managed_node_statuses_no_observations(
    monkeypatch,
    create_managed_node,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    mn = create_managed_node()
    ManagedNodeStatus.objects.filter(node=mn).delete()

    result = update_managed_node_statuses()

    assert result["sending"] == 0
    st = ManagedNodeStatus.objects.get(node=mn)
    assert st.last_packet_ingested_at is None
    assert st.is_sending_data is False


@pytest.mark.django_db
def test_update_managed_node_statuses_updates_existing_row(
    monkeypatch,
    create_managed_node,
    create_packet_observation,
):
    monkeypatch.setenv("SCHEDULE_TRACEROUTE_SOURCE_RECENCY_SECONDS", "600")
    mn = create_managed_node()
    ManagedNodeStatus.objects.update_or_create(
        node=mn,
        defaults={
            "last_packet_ingested_at": None,
            "is_sending_data": False,
        },
    )

    create_packet_observation(observer=mn)

    result = update_managed_node_statuses()

    assert result["updated"] >= 1
    st = ManagedNodeStatus.objects.get(node=mn)
    assert st.last_packet_ingested_at is not None
    assert st.is_sending_data is True
