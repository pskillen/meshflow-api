"""API tests for path-tracing endpoints."""

from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from common.protocol import Protocol
from meshcore_packet_path.models import MeshCorePathSegmentResolution, SegmentStatus
from meshcore_packet_path.services.rollup import collect_path_edge_buckets_for_hour


@pytest.fixture
def api_client(create_user):
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture
def staff_client(create_user):
    client = APIClient()
    user = create_user(is_staff=True, is_superuser=True)
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
def test_edges_list_requires_auth():
    response = APIClient().get(reverse("meshcore-path-tracing-edges"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_edges_list_includes_direction(api_client, path_observation):
    client, _ = api_client
    hour = path_observation["hour_start"]
    collect_path_edge_buckets_for_hour(hour)

    response = client.get(reverse("meshcore-path-tracing-edges"))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    row = response.data["results"][0]
    assert row["direction"] == "list_order"


@pytest.mark.django_db
def test_edges_filter_from_hash(api_client, path_observation):
    client, _ = api_client
    hour = path_observation["hour_start"]
    collect_path_edge_buckets_for_hour(hour)

    response = client.get(reverse("meshcore-path-tracing-edges"), {"from_hash": "aa"})
    assert response.status_code == status.HTTP_200_OK
    for row in response.data["results"]:
        assert row["from_hash"] == "aa"


@pytest.mark.django_db
def test_segments_list_filter_hash_mode(api_client):
    client, _ = api_client
    MeshCorePathSegmentResolution.objects.create(
        segment_hash="a1",
        hash_mode=2,
        hash_size=1,
        status=SegmentStatus.UNKNOWN,
    )
    MeshCorePathSegmentResolution.objects.create(
        segment_hash="b2",
        hash_mode=0,
        hash_size=2,
        status=SegmentStatus.UNKNOWN,
    )

    response = client.get(reverse("meshcore-path-tracing-segments"), {"hash_mode": 2})
    assert response.status_code == status.HTTP_200_OK
    hashes = {r["segment_hash"] for r in response.data["results"]}
    assert hashes == {"a1"}


@pytest.mark.django_db
def test_segment_patch_staff_manual_admin(staff_client, create_observed_node):
    client, _ = staff_client
    node = create_observed_node(protocol=Protocol.MESHCORE, mc_pubkey="c" * 64)
    seg = MeshCorePathSegmentResolution.objects.create(
        segment_hash="feed",
        status=SegmentStatus.UNKNOWN,
    )

    url = reverse("meshcore-path-tracing-segment-detail", kwargs={"pk": seg.pk})
    response = client.patch(
        url,
        {"node_id_str": f"mc:{node.mc_pubkey}", "status": "resolved"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    seg.refresh_from_db()
    assert seg.source == "manual_admin"
    assert seg.observed_node_id == node.internal_id
    assert seg.status == SegmentStatus.RESOLVED
    assert seg.resolver_version == 2


@pytest.mark.django_db
def test_segment_patch_forbidden_for_non_staff(api_client):
    client, _ = api_client
    seg = MeshCorePathSegmentResolution.objects.create(segment_hash="nope")
    url = reverse("meshcore-path-tracing-segment-detail", kwargs={"pk": seg.pk})
    response = client.patch(url, {"status": "resolved"}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN
