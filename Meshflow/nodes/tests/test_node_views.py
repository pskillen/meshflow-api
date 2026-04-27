from django.urls import reverse
from django.utils import timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import NodeAuth, NodeLatestStatus, NodeOwnerClaim
from nodes.tasks import update_managed_node_statuses


@pytest.mark.django_db
def test_managed_node_list_view(create_managed_node, create_user):
    """Test managed node list view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create some test nodes
    node1 = create_managed_node(owner=user)  # noqa: F841
    node2 = create_managed_node(owner=user)  # noqa: F841

    # Test GET request
    response = client.get(reverse("managed-nodes-list"))
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 2


@pytest.mark.django_db
def test_managed_node_detail_view(create_managed_node, create_user):
    """Test managed node detail view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create a test node
    node = create_managed_node(owner=user)

    # Test GET request
    response = client.get(reverse("managed-nodes-detail", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["node_id"] == node.node_id


@pytest.mark.django_db
def test_managed_nodes_status_fields_only_returned_with_include_status(
    create_managed_node,
    create_observed_node,
    create_packet_observation,
    create_user,
):
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    now = timezone.now()
    managed = create_managed_node(owner=user, node_id=123450001, allow_auto_traceroute=True)
    observed = create_observed_node(
        node_id=managed.node_id, node_id_str=meshtastic_id_to_hex(managed.node_id), last_heard=now
    )
    NodeLatestStatus.objects.create(node=observed)
    observation = create_packet_observation(observer=managed)
    observation.upload_time = now
    observation.save(update_fields=["upload_time"])
    update_managed_node_statuses()

    list_url = reverse("managed-nodes-list")
    response_without_status = client.get(list_url)
    assert response_without_status.status_code == status.HTTP_200_OK
    first_without_status = response_without_status.data["results"][0]
    assert "last_packet_ingested_at" not in first_without_status
    assert "packets_last_hour" not in first_without_status
    assert "packets_last_24h" not in first_without_status
    assert "radio_last_heard" not in first_without_status
    assert "is_eligible_traceroute_source" not in first_without_status

    response_with_status = client.get(list_url, {"include": "status"})
    assert response_with_status.status_code == status.HTTP_200_OK
    first_with_status = response_with_status.data["results"][0]
    assert first_with_status["last_packet_ingested_at"] is not None
    assert first_with_status["packets_last_hour"] == 1
    assert first_with_status["packets_last_24h"] == 1
    assert first_with_status["radio_last_heard"] is not None
    assert first_with_status["is_eligible_traceroute_source"] is True

    detail_url = reverse("managed-nodes-detail", kwargs={"node_id": managed.node_id})
    detail_response = client.get(detail_url, {"include": "status"})
    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.data["packets_last_hour"] == 1

    mine_url = reverse("managed-nodes-mine")
    mine_response = client.get(mine_url, {"include": "status"})
    assert mine_response.status_code == status.HTTP_200_OK
    assert mine_response.data["results"][0]["packets_last_24h"] == 1


@pytest.mark.django_db
def test_observed_node_list_view(create_observed_node, create_user):
    """Test observed node list view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create some test nodes
    node1 = create_observed_node()  # noqa: F841
    node2 = create_observed_node()  # noqa: F841

    # Test GET request
    response = client.get(reverse("observed-node-list"))
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 2


@pytest.mark.django_db
def test_observed_node_detail_view(create_observed_node, create_user):
    """Test observed node detail view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create a test node
    node = create_observed_node()

    # Test GET request
    response = client.get(reverse("observed-node-detail", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["node_id"] == node.node_id


@pytest.mark.django_db
def test_node_api_key_list_view(create_node_api_key, create_user):
    """Test node API key list view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create some test API keys
    key1 = create_node_api_key(owner=user)  # noqa: F841
    key2 = create_node_api_key(owner=user)  # noqa: F841

    # Test GET request
    response = client.get(reverse("api-keys-list"))
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 2


@pytest.mark.django_db
def test_node_api_key_detail_view(create_node_api_key, create_user):
    """Test node API key detail view."""
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    # Create a test API key
    api_key = create_node_api_key(owner=user)

    # Test GET request
    response = client.get(reverse("api-keys-detail", kwargs={"pk": api_key.id}))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == str(api_key.id)


@pytest.mark.django_db
def test_claim_post_rejected_when_node_owned_by_another_user(create_observed_node, create_user):
    """POST to create claim returns 400 when node is already claimed by another user."""
    owner = create_user()
    other_user = create_user()
    node_id = 111222333444
    node = create_observed_node(
        node_id=node_id,
        node_id_str=meshtastic_id_to_hex(node_id),
        claimed_by=owner,
    )

    client = APIClient()
    client.force_authenticate(user=other_user)

    response = client.post(
        reverse("observed-node-claim", kwargs={"node_id": node.node_id}),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already claimed" in response.data["detail"].lower()


@pytest.mark.django_db
def test_claim_delete_clears_claimed_by_when_owner(create_observed_node, create_user):
    owner = create_user()
    node_id = 555001001
    node = create_observed_node(
        node_id=node_id,
        node_id_str=meshtastic_id_to_hex(node_id),
        claimed_by=owner,
    )
    NodeOwnerClaim.objects.create(node=node, user=owner, claim_key="k", accepted_at=timezone.now())

    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.delete(reverse("observed-node-claim", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_204_NO_CONTENT

    node.refresh_from_db()
    assert node.claimed_by_id is None
    assert not NodeOwnerClaim.objects.filter(node=node, user=owner).exists()


@pytest.mark.django_db
def test_claim_delete_pending_does_not_require_claimed_by(create_observed_node, create_user):
    owner = create_user()
    node_id = 555001002
    node = create_observed_node(
        node_id=node_id,
        node_id_str=meshtastic_id_to_hex(node_id),
        claimed_by=None,
    )
    NodeOwnerClaim.objects.create(node=node, user=owner, claim_key="k2", accepted_at=None)

    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.delete(reverse("observed-node-claim", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_204_NO_CONTENT
    node.refresh_from_db()
    assert node.claimed_by_id is None


@pytest.mark.django_db
def test_claim_delete_does_not_clear_other_users_claimed_by(create_observed_node, create_user):
    owner = create_user()
    other = create_user()
    node_id = 555001003
    node = create_observed_node(
        node_id=node_id,
        node_id_str=meshtastic_id_to_hex(node_id),
        claimed_by=other,
    )
    NodeOwnerClaim.objects.create(node=node, user=owner, claim_key="k3", accepted_at=None)

    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.delete(reverse("observed-node-claim", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_204_NO_CONTENT

    node.refresh_from_db()
    assert node.claimed_by_id == other.id


@pytest.mark.django_db
def test_claim_delete_non_owner_no_claim_returns_404(create_observed_node, create_user):
    owner = create_user()
    other = create_user()
    node_id = 555001004
    node = create_observed_node(
        node_id=node_id,
        node_id_str=meshtastic_id_to_hex(node_id),
        claimed_by=owner,
    )
    NodeOwnerClaim.objects.create(node=node, user=owner, claim_key="k4", accepted_at=timezone.now())

    client = APIClient()
    client.force_authenticate(user=other)
    response = client.delete(reverse("observed-node-claim", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert NodeOwnerClaim.objects.filter(node=node, user=owner).exists()
    node.refresh_from_db()
    assert node.claimed_by_id == owner.id


@pytest.mark.django_db
def test_claim_delete_staff_without_own_claim_returns_404(create_observed_node, create_user):
    owner = create_user()
    staff = create_user(is_staff=True)
    node_id = 555001005
    node = create_observed_node(
        node_id=node_id,
        node_id_str=meshtastic_id_to_hex(node_id),
        claimed_by=owner,
    )
    NodeOwnerClaim.objects.create(node=node, user=owner, claim_key="k5", accepted_at=timezone.now())

    client = APIClient()
    client.force_authenticate(user=staff)
    response = client.delete(reverse("observed-node-claim", kwargs={"node_id": node.node_id}))
    assert response.status_code == status.HTTP_404_NOT_FOUND


def _managed_node_json_payload(*, node_id, owner, constellation, ch0, ch1):
    return {
        "node_id": node_id,
        "name": "Test MN",
        "owner_id": owner.id,
        "constellation_id": constellation.id,
        "channel_0": ch0.id,
        "channel_1": ch1.id,
    }


@pytest.mark.django_db
def test_managed_node_soft_delete_owner_removes_node_auth_and_excludes_from_list(
    create_user, create_constellation, create_managed_node, create_node_api_key
):
    from constellations.models import MessageChannel

    owner = create_user()
    constellation = create_constellation(created_by=owner)
    ch0 = MessageChannel.objects.create(name="c0", constellation=constellation)
    ch1 = MessageChannel.objects.create(name="c1", constellation=constellation)
    node_id = 777001001
    mn = create_managed_node(
        owner=owner,
        constellation=constellation,
        node_id=node_id,
        channel_0=ch0,
        channel_1=ch1,
    )
    api_key = create_node_api_key(owner=owner, constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=mn)

    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("managed-nodes-detail", kwargs={"node_id": mn.node_id})
    assert client.delete(url).status_code == status.HTTP_204_NO_CONTENT

    assert not NodeAuth.objects.filter(node=mn).exists()
    mn.refresh_from_db()
    assert mn.deleted_at is not None

    list_resp = client.get(reverse("managed-nodes-list"))
    assert list_resp.status_code == status.HTTP_200_OK
    ids = {row["node_id"] for row in list_resp.data["results"]}
    assert node_id not in ids

    detail_resp = client.get(url)
    assert detail_resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_managed_node_soft_delete_staff(create_user, create_constellation, create_managed_node, create_node_api_key):
    from constellations.models import MessageChannel

    owner = create_user()
    staff = create_user(is_staff=True)
    constellation = create_constellation(created_by=owner)
    ch0 = MessageChannel.objects.create(name="c0b", constellation=constellation)
    ch1 = MessageChannel.objects.create(name="c1b", constellation=constellation)
    mn = create_managed_node(
        owner=owner,
        constellation=constellation,
        node_id=777001002,
        channel_0=ch0,
        channel_1=ch1,
    )
    api_key = create_node_api_key(owner=owner, constellation=constellation)
    NodeAuth.objects.create(api_key=api_key, node=mn)

    client = APIClient()
    client.force_authenticate(user=staff)
    url = reverse("managed-nodes-detail", kwargs={"node_id": mn.node_id})
    assert client.delete(url).status_code == status.HTTP_204_NO_CONTENT
    mn.refresh_from_db()
    assert mn.deleted_at is not None


@pytest.mark.django_db
def test_managed_node_delete_forbidden_for_non_owner_non_staff(create_user, create_constellation, create_managed_node):
    from constellations.models import MessageChannel

    owner = create_user()
    other = create_user()
    constellation = create_constellation(created_by=owner)
    ch0 = MessageChannel.objects.create(name="c0c", constellation=constellation)
    ch1 = MessageChannel.objects.create(name="c1c", constellation=constellation)
    mn = create_managed_node(
        owner=owner,
        constellation=constellation,
        node_id=777001003,
        channel_0=ch0,
        channel_1=ch1,
    )

    client = APIClient()
    client.force_authenticate(user=other)
    url = reverse("managed-nodes-detail", kwargs={"node_id": mn.node_id})
    assert client.delete(url).status_code == status.HTTP_403_FORBIDDEN
    mn.refresh_from_db()
    assert mn.deleted_at is None


@pytest.mark.django_db
def test_managed_node_create_rejected_when_soft_deleted_row_exists(
    create_user, create_constellation, create_managed_node
):
    from constellations.models import MessageChannel

    owner = create_user()
    constellation = create_constellation(created_by=owner)
    ch0 = MessageChannel.objects.create(name="c0d", constellation=constellation)
    ch1 = MessageChannel.objects.create(name="c1d", constellation=constellation)
    node_id = 777001004
    mn = create_managed_node(
        owner=owner,
        constellation=constellation,
        node_id=node_id,
        channel_0=ch0,
        channel_1=ch1,
    )
    mn.deleted_at = timezone.now()
    mn.save(update_fields=["deleted_at"])

    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.post(
        reverse("managed-nodes-list"),
        _managed_node_json_payload(node_id=node_id, owner=owner, constellation=constellation, ch0=ch0, ch1=ch1),
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "previously removed" in str(response.data).lower()


@pytest.mark.django_db
def test_managed_node_create_rejected_when_active_row_exists(create_user, create_constellation, create_managed_node):
    from constellations.models import MessageChannel

    owner = create_user()
    constellation = create_constellation(created_by=owner)
    ch0 = MessageChannel.objects.create(name="c0e", constellation=constellation)
    ch1 = MessageChannel.objects.create(name="c1e", constellation=constellation)
    node_id = 777001005
    create_managed_node(
        owner=owner,
        constellation=constellation,
        node_id=node_id,
        channel_0=ch0,
        channel_1=ch1,
    )

    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.post(
        reverse("managed-nodes-list"),
        _managed_node_json_payload(node_id=node_id, owner=owner, constellation=constellation, ch0=ch0, ch1=ch1),
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already exists" in str(response.data).lower()
