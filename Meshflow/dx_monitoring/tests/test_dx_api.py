"""Tests for DX monitoring visibility API."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient

import constellations.tests.conftest  # noqa: F401
import nodes.tests.conftest  # noqa: F401
import packets.tests.conftest  # noqa: F401
import users.tests.conftest  # noqa: F401
from dx_monitoring.models import DxEvent, DxEventObservation, DxEventState, DxNodeMetadata, DxReasonCode


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_dx_events_list_forbidden_for_non_staff(api_client, create_user, create_constellation, create_observed_node):
    user = create_user(is_staff=False)
    api_client.force_authenticate(user=user)
    c = create_constellation()
    dest = create_observed_node(node_id=0xABCD0001)
    now = timezone.now()
    DxEvent.objects.create(
        constellation=c,
        destination=dest,
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
    )
    url = reverse("dxevent-list")
    r = api_client.get(url)
    assert r.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_dx_events_list_staff_ok(api_client, create_user, create_constellation, create_observed_node):
    staff = create_user(is_staff=True)
    api_client.force_authenticate(user=staff)
    c = create_constellation()
    dest = create_observed_node(node_id=0xABCD0002)
    now = timezone.now()
    ev = DxEvent.objects.create(
        constellation=c,
        destination=dest,
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
    )
    url = reverse("dxevent-list")
    r = api_client.get(url)
    assert r.status_code == status.HTTP_200_OK
    assert r.data["count"] == 1
    row = r.data["results"][0]
    assert row["id"] == str(ev.id)
    assert row["reason_code"] == DxReasonCode.NEW_DISTANT_NODE
    assert row["destination"]["node_id"] == dest.node_id
    assert row["destination"]["dx_metadata"]["exclude_from_detection"] is False
    assert row["evidence_count"] == 0


@pytest.mark.django_db
def test_dx_events_filter_reason_and_destination(api_client, create_user, create_constellation, create_observed_node):
    staff = create_user(is_staff=True)
    api_client.force_authenticate(user=staff)
    c = create_constellation()
    d1 = create_observed_node(node_id=0x11111101)
    d2 = create_observed_node(node_id=0x22222202)
    now = timezone.now()
    DxEvent.objects.create(
        constellation=c,
        destination=d1,
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
    )
    DxEvent.objects.create(
        constellation=c,
        destination=d2,
        reason_code=DxReasonCode.RETURNED_DX_NODE,
        state=DxEventState.CLOSED,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now - timedelta(hours=1),
    )
    url = reverse("dxevent-list")
    r = api_client.get(url, {"reason_code": DxReasonCode.RETURNED_DX_NODE})
    assert r.data["count"] == 1
    assert r.data["results"][0]["destination"]["node_id"] == d2.node_id

    r2 = api_client.get(url, {"destination_node_id": d1.node_id})
    assert r2.data["count"] == 1
    assert r2.data["results"][0]["reason_code"] == DxReasonCode.NEW_DISTANT_NODE


@pytest.mark.django_db
def test_dx_event_detail_includes_observations(
    api_client,
    create_user,
    create_constellation,
    create_observed_node,
    create_managed_node,
    create_packet_observation,
    create_node_info_packet,
):
    staff = create_user(is_staff=True)
    api_client.force_authenticate(user=staff)
    observer = create_managed_node()
    c = create_constellation()
    dest = create_observed_node(node_id=0x33333303)
    now = timezone.now()
    ev = DxEvent.objects.create(
        constellation=c,
        destination=dest,
        reason_code=DxReasonCode.DISTANT_OBSERVATION,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
        last_observer=observer,
    )
    pkt = create_node_info_packet(packet_id=42, from_int=dest.node_id, from_str=dest.node_id_str)
    obs_po = create_packet_observation(packet=pkt, observer=observer)
    DxEventObservation.objects.create(
        event=ev,
        raw_packet=pkt,
        packet_observation=obs_po,
        observer=observer,
        observed_at=now,
        distance_km=123.4,
        metadata={"k": "v"},
    )

    url = reverse("dxevent-detail", kwargs={"pk": str(ev.id)})
    r = api_client.get(url)
    assert r.status_code == status.HTTP_200_OK
    assert len(r.data["observations"]) == 1
    o0 = r.data["observations"][0]
    assert o0["distance_km"] == 123.4
    assert str(o0["raw_packet"]) == str(pkt.id)
    assert o0["observer"]["node_id"] == observer.node_id


@pytest.mark.django_db
def test_dx_node_exclusion_post_staff(api_client, create_user, create_observed_node):
    staff = create_user(is_staff=True)
    api_client.force_authenticate(user=staff)
    dest = create_observed_node(node_id=0x44444404)
    url = reverse("dx-node-exclusion")
    r = api_client.post(
        url,
        {"node_id": dest.node_id, "exclude_from_detection": True, "exclude_notes": "test mobile"},
        format="json",
    )
    assert r.status_code == status.HTTP_200_OK
    assert r.data["exclude_from_detection"] is True
    assert r.data["exclude_notes"] == "test mobile"
    meta = DxNodeMetadata.objects.get(observed_node=dest)
    assert meta.exclude_from_detection is True


@pytest.mark.django_db
def test_dx_node_exclusion_forbidden_non_staff(api_client, create_user, create_observed_node):
    user = create_user(is_staff=False)
    api_client.force_authenticate(user=user)
    dest = create_observed_node(node_id=0x55555505)
    url = reverse("dx-node-exclusion")
    r = api_client.post(
        url,
        {"node_id": dest.node_id, "exclude_from_detection": True},
        format="json",
    )
    assert r.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_dx_node_exclusion_unknown_node(api_client, create_user):
    staff = create_user(is_staff=True)
    api_client.force_authenticate(user=staff)
    url = reverse("dx-node-exclusion")
    r = api_client.post(
        url,
        {"node_id": 999999999999, "exclude_from_detection": True},
        format="json",
    )
    assert r.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_dx_event_list_shows_exclusion_on_destination(
    api_client, create_user, create_constellation, create_observed_node
):
    staff = create_user(is_staff=True)
    api_client.force_authenticate(user=staff)
    c = create_constellation()
    dest = create_observed_node(node_id=0x66666606)
    DxNodeMetadata.objects.create(observed_node=dest, exclude_from_detection=True, exclude_notes="n")
    now = timezone.now()
    DxEvent.objects.create(
        constellation=c,
        destination=dest,
        reason_code=DxReasonCode.NEW_DISTANT_NODE,
        state=DxEventState.ACTIVE,
        first_observed_at=now,
        last_observed_at=now,
        active_until=now + timedelta(hours=1),
    )
    url = reverse("dxevent-list")
    r = api_client.get(url)
    assert r.data["results"][0]["destination"]["dx_metadata"]["exclude_from_detection"] is True
    assert r.data["results"][0]["destination"]["dx_metadata"]["exclude_notes"] == "n"
