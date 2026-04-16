"""Eligibility, presence clearing, suppression list."""

from django.core.exceptions import ValidationError
from django.utils import timezone

import pytest

import nodes.tests.conftest  # noqa: F401
from mesh_monitoring.eligibility import user_can_watch
from mesh_monitoring.models import NodePresence, NodeWatch
from mesh_monitoring.services import clear_presence_on_packet_from_node
from mesh_monitoring.suppression import suppressed_observed_node_ids
from nodes.constants import INFRASTRUCTURE_ROLES
from nodes.models import RoleSource


@pytest.mark.django_db
def test_user_can_watch_claimed(create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(claimed_by=user)
    assert user_can_watch(user, obs) is True


@pytest.mark.django_db
def test_user_can_watch_infrastructure_role(create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(role=INFRASTRUCTURE_ROLES[0], claimed_by=None)
    assert user_can_watch(user, obs) is True


@pytest.mark.django_db
def test_user_cannot_watch_other_client(create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(role=RoleSource.CLIENT, claimed_by=None)
    assert user_can_watch(user, obs) is False


@pytest.mark.django_db
def test_clear_presence_on_packet_from_node_clears_observability_only(create_observed_node):
    obs = create_observed_node()
    NodePresence.objects.create(
        observed_node=obs,
        tr_sent_count=3,
        suspected_offline_at=timezone.now(),
        last_tr_sent=timezone.now(),
        last_zero_sources_at=timezone.now(),
    )
    clear_presence_on_packet_from_node(obs)
    p = NodePresence.objects.get(observed_node=obs)
    assert p.tr_sent_count == 0
    assert p.suspected_offline_at is None
    assert p.last_tr_sent is None
    assert p.last_zero_sources_at is None
    assert p.is_offline is False


@pytest.mark.django_db
def test_clear_presence_on_packet_from_node(create_observed_node):
    obs = create_observed_node()
    NodePresence.objects.create(
        observed_node=obs,
        verification_started_at=timezone.now(),
        offline_confirmed_at=timezone.now(),
        is_offline=True,
    )
    clear_presence_on_packet_from_node(obs)
    p = NodePresence.objects.get(observed_node=obs)
    assert p.verification_started_at is None
    assert p.offline_confirmed_at is None
    assert p.suspected_offline_at is None
    assert p.last_tr_sent is None
    assert p.last_zero_sources_at is None
    assert p.tr_sent_count == 0
    assert p.is_offline is False
    assert p.observed_online_at is not None


@pytest.mark.django_db
def test_clear_presence_on_packet_from_node_clears_last_verification_notify_at(create_observed_node):
    obs = create_observed_node()
    NodePresence.objects.create(
        observed_node=obs,
        last_verification_notify_at=timezone.now(),
    )
    clear_presence_on_packet_from_node(obs)
    p = NodePresence.objects.get(observed_node=obs)
    assert p.last_verification_notify_at is None


@pytest.mark.django_db
def test_suppressed_observed_node_ids(create_observed_node):
    obs = create_observed_node()
    NodePresence.objects.create(observed_node=obs, verification_started_at=timezone.now())
    ids = list(suppressed_observed_node_ids())
    assert obs.pk in ids


@pytest.mark.django_db
def test_nodewatch_save_validates_eligibility(create_user, create_observed_node):
    user = create_user()
    obs = create_observed_node(role=RoleSource.CLIENT, claimed_by=None)
    with pytest.raises(ValidationError):
        NodeWatch.objects.create(user=user, observed_node=obs, offline_after=60, enabled=True)
