"""Tests for backfill_observednode_created_at management command."""

from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone

import pytest

from nodes.models import ObservedNode

pytest_plugins = ["packets.tests.conftest"]


@pytest.mark.django_db
def test_backfill_sets_created_at_when_null(create_observed_node, create_raw_packet):
    """Rows with created_at NULL get earliest packet first_reported_time."""
    old = timezone.now() - timedelta(days=100)
    node = create_observed_node()
    ObservedNode.objects.filter(pk=node.pk).update(created_at=None)
    create_raw_packet(first_reported_time=old)

    call_command("backfill_observednode_created_at")

    node.refresh_from_db()
    assert node.created_at == old


@pytest.mark.django_db
def test_backfill_skips_when_created_at_set(create_observed_node, create_raw_packet):
    """Default does not overwrite existing created_at."""
    old_packet = timezone.now() - timedelta(days=200)
    recent_created = timezone.now() - timedelta(days=1)
    node = create_observed_node()
    ObservedNode.objects.filter(pk=node.pk).update(created_at=recent_created)
    create_raw_packet(first_reported_time=old_packet)

    call_command("backfill_observednode_created_at")

    node.refresh_from_db()
    assert node.created_at == recent_created


@pytest.mark.django_db
def test_backfill_overwrite_updates_from_packets(create_observed_node, create_raw_packet):
    """--overwrite sets created_at from packets even when already set."""
    old_packet = timezone.now() - timedelta(days=200)
    recent_created = timezone.now() - timedelta(days=1)
    node = create_observed_node()
    ObservedNode.objects.filter(pk=node.pk).update(created_at=recent_created)
    create_raw_packet(first_reported_time=old_packet)

    call_command("backfill_observednode_created_at", "--overwrite")

    node.refresh_from_db()
    assert node.created_at == old_packet


@pytest.mark.django_db
def test_backfill_dry_run_does_not_write(create_observed_node, create_raw_packet):
    """Dry run leaves created_at unchanged."""
    old = timezone.now() - timedelta(days=50)
    node = create_observed_node()
    ObservedNode.objects.filter(pk=node.pk).update(created_at=None)
    create_raw_packet(first_reported_time=old)

    call_command("backfill_observednode_created_at", "--dry-run")

    node.refresh_from_db()
    assert node.created_at is None
