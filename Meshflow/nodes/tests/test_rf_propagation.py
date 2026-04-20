from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from common.mesh_node_helpers import meshtastic_id_to_hex
from nodes.models import AntennaPattern, NodeRfProfile, NodeRfPropagationRender
from nodes.serializers import NodeRfProfileSerializer


@pytest.fixture
def stub_render_task():
    """Replace ``render_rf_propagation.delay`` with a no-op so endpoint tests
    don't trigger the real engine via Celery ``ALWAYS_EAGER``."""
    with patch("rf_propagation.tasks.render_rf_propagation.delay") as mock_delay:
        yield mock_delay


def _rf_profile_fields(**overrides):
    data = {
        "rf_latitude": 55.861,
        "rf_longitude": -4.251,
        "rf_altitude_m": 80.0,
        "antenna_height_m": 6.0,
        "antenna_gain_dbi": 3.0,
        "tx_power_dbm": 27.0,
        "rf_frequency_mhz": 869.525,
        "antenna_pattern": AntennaPattern.OMNI,
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_node_rf_profile_one_to_one(create_observed_node):
    node = create_observed_node(
        node_id=801_801_801,
        node_id_str=meshtastic_id_to_hex(801_801_801),
    )
    NodeRfProfile.objects.create(observed_node=node, antenna_pattern=AntennaPattern.OMNI)
    with pytest.raises(IntegrityError):
        NodeRfProfile.objects.create(observed_node=node, antenna_pattern=AntennaPattern.OMNI)


@pytest.mark.django_db
def test_node_rf_propagation_render_create(create_observed_node):
    node = create_observed_node(
        node_id=802_802_802,
        node_id_str=meshtastic_id_to_hex(802_802_802),
    )
    row = NodeRfPropagationRender.objects.create(observed_node=node)
    assert row.status == NodeRfPropagationRender.Status.PENDING
    assert node.latest_rf_render() == row


@pytest.mark.django_db
def test_rf_profile_serializer_hides_private_for_anonymous(create_observed_node, create_user):
    owner = create_user()
    node = create_observed_node(
        node_id=803_803_803,
        node_id_str=meshtastic_id_to_hex(803_803_803),
        claimed_by=owner,
    )
    profile = NodeRfProfile.objects.create(
        observed_node=node,
        rf_latitude=55.0,
        rf_longitude=-4.0,
        rf_altitude_m=100.0,
        antenna_pattern=AntennaPattern.OMNI,
    )
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = AnonymousUser()
    data = NodeRfProfileSerializer(profile, context={"request": request}).data
    assert "rf_latitude" not in data
    assert "rf_longitude" not in data
    assert "rf_altitude_m" not in data


@pytest.mark.django_db
def test_rf_profile_serializer_hides_private_for_stranger(create_observed_node, create_user):
    owner = create_user()
    stranger = create_user()
    node = create_observed_node(
        node_id=804_804_804,
        node_id_str=meshtastic_id_to_hex(804_804_804),
        claimed_by=owner,
    )
    profile = NodeRfProfile.objects.create(
        observed_node=node,
        rf_latitude=55.0,
        rf_longitude=-4.0,
        rf_altitude_m=100.0,
        antenna_pattern=AntennaPattern.OMNI,
    )
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = stranger
    data = NodeRfProfileSerializer(profile, context={"request": request}).data
    assert "rf_latitude" not in data


@pytest.mark.django_db
def test_rf_profile_serializer_shows_private_for_owner(create_observed_node, create_user):
    owner = create_user()
    node = create_observed_node(
        node_id=805_805_805,
        node_id_str=meshtastic_id_to_hex(805_805_805),
        claimed_by=owner,
    )
    profile = NodeRfProfile.objects.create(
        observed_node=node,
        rf_latitude=55.0,
        rf_longitude=-4.0,
        rf_altitude_m=100.0,
        antenna_pattern=AntennaPattern.OMNI,
    )
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = owner
    data = NodeRfProfileSerializer(profile, context={"request": request}).data
    assert data["rf_latitude"] == 55.0
    assert data["rf_longitude"] == -4.0
    assert data["rf_altitude_m"] == 100.0


@pytest.mark.django_db
def test_rf_profile_serializer_shows_private_for_staff(create_observed_node, create_user):
    staff = create_user(is_staff=True)
    node = create_observed_node(
        node_id=806_806_806,
        node_id_str=meshtastic_id_to_hex(806_806_806),
    )
    profile = NodeRfProfile.objects.create(
        observed_node=node,
        rf_latitude=55.0,
        rf_longitude=-4.0,
        rf_altitude_m=100.0,
        antenna_pattern=AntennaPattern.OMNI,
    )
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = staff
    data = NodeRfProfileSerializer(profile, context={"request": request}).data
    assert data["rf_latitude"] == 55.0


@pytest.mark.django_db
def test_rf_profile_get_empty_returns_204(create_observed_node, create_user):
    user = create_user()
    node = create_observed_node(
        node_id=807_807_807,
        node_id_str=meshtastic_id_to_hex(807_807_807),
    )
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("observed-node-rf-profile", kwargs={"node_id": node.node_id})
    response = client.get(url)
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_rf_profile_get_after_patch(create_observed_node, create_user):
    owner = create_user()
    node = create_observed_node(
        node_id=808_808_808,
        node_id_str=meshtastic_id_to_hex(808_808_808),
        claimed_by=owner,
    )
    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("observed-node-rf-profile", kwargs={"node_id": node.node_id})
    patch = client.patch(
        url,
        {
            "antenna_pattern": "directional",
            "antenna_azimuth_deg": 90.0,
            "antenna_beamwidth_deg": 45.0,
            "tx_power_dbm": 22.0,
            "rf_latitude": 10.0,
            "rf_longitude": 20.0,
        },
        format="json",
    )
    assert patch.status_code == status.HTTP_200_OK
    get_r = client.get(url)
    assert get_r.status_code == status.HTTP_200_OK
    assert get_r.data["antenna_pattern"] == "directional"
    assert get_r.data["tx_power_dbm"] == 22.0
    assert get_r.data["rf_latitude"] == 10.0


@pytest.mark.django_db
def test_rf_profile_patch_owner_staff_stranger_unauth(create_observed_node, create_user):
    owner = create_user()
    stranger = create_user()
    staff = create_user(is_staff=True)
    node = create_observed_node(
        node_id=809_809_809,
        node_id_str=meshtastic_id_to_hex(809_809_809),
        claimed_by=owner,
    )
    url = reverse("observed-node-rf-profile", kwargs={"node_id": node.node_id})

    client = APIClient()
    response = client.patch(url, {"tx_power_dbm": 10.0}, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    client.force_authenticate(user=stranger)
    response = client.patch(url, {"tx_power_dbm": 10.0}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN

    client.force_authenticate(user=owner)
    response = client.patch(url, {"tx_power_dbm": 12.0}, format="json")
    assert response.status_code == status.HTTP_200_OK

    client.force_authenticate(user=staff)
    response = client.patch(url, {"tx_power_dbm": 14.0}, format="json")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_rf_propagation_get_none_then_pending(create_observed_node, create_user, stub_render_task):
    owner = create_user()
    node = create_observed_node(
        node_id=810_810_810,
        node_id_str=meshtastic_id_to_hex(810_810_810),
        claimed_by=owner,
    )
    NodeRfProfile.objects.create(observed_node=node, **_rf_profile_fields())
    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("observed-node-rf-propagation", kwargs={"node_id": node.node_id})
    r0 = client.get(url)
    assert r0.status_code == status.HTTP_200_OK
    assert r0.data == {"status": "none"}

    rec_url = reverse("observed-node-rf-propagation-recompute", kwargs={"node_id": node.node_id})
    r1 = client.post(rec_url, {}, format="json")
    assert r1.status_code == status.HTTP_201_CREATED
    assert r1.data["status"] == "pending"
    assert stub_render_task.call_count == 1

    r2 = client.get(url)
    assert r2.status_code == status.HTTP_200_OK
    assert r2.data["status"] == "pending"


@pytest.mark.django_db
def test_rf_propagation_recompute_forbidden_stranger(create_observed_node, create_user):
    owner = create_user()
    stranger = create_user()
    node = create_observed_node(
        node_id=811_811_811,
        node_id_str=meshtastic_id_to_hex(811_811_811),
        claimed_by=owner,
    )
    client = APIClient()
    client.force_authenticate(user=stranger)
    url = reverse("observed-node-rf-propagation-recompute", kwargs={"node_id": node.node_id})
    response = client.post(url, {}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_rf_propagation_recompute_creates_row(create_observed_node, create_user, stub_render_task):
    owner = create_user()
    node = create_observed_node(
        node_id=812_812_812,
        node_id_str=meshtastic_id_to_hex(812_812_812),
        claimed_by=owner,
    )
    NodeRfProfile.objects.create(observed_node=node, **_rf_profile_fields())
    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("observed-node-rf-propagation-recompute", kwargs={"node_id": node.node_id})
    response = client.post(url, {}, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert NodeRfPropagationRender.objects.filter(observed_node=node).count() == 1
    stub_render_task.assert_called_once()


@pytest.mark.django_db
def test_rf_propagation_recompute_400_when_no_profile(create_observed_node, create_user, stub_render_task):
    owner = create_user()
    node = create_observed_node(
        node_id=812_812_813,
        node_id_str=meshtastic_id_to_hex(812_812_813),
        claimed_by=owner,
    )
    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("observed-node-rf-propagation-recompute", kwargs={"node_id": node.node_id})
    response = client.post(url, {}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    stub_render_task.assert_not_called()


@pytest.mark.django_db
def test_rf_propagation_recompute_dedup_returns_in_flight(create_observed_node, create_user, stub_render_task):
    owner = create_user()
    node = create_observed_node(
        node_id=812_812_814,
        node_id_str=meshtastic_id_to_hex(812_812_814),
        claimed_by=owner,
    )
    NodeRfProfile.objects.create(observed_node=node, **_rf_profile_fields())
    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("observed-node-rf-propagation-recompute", kwargs={"node_id": node.node_id})

    first = client.post(url, {}, format="json")
    assert first.status_code == status.HTTP_201_CREATED
    second = client.post(url, {}, format="json")
    assert second.status_code == status.HTTP_200_OK
    assert second.data["created_at"] == first.data["created_at"]
    assert second.data["input_hash"] == first.data["input_hash"]
    assert NodeRfPropagationRender.objects.filter(observed_node=node).count() == 1
    assert stub_render_task.call_count == 1


@pytest.mark.django_db
def test_rf_propagation_recompute_cache_hit_reuses_asset(settings, create_observed_node, create_user, stub_render_task):
    import tempfile
    from pathlib import Path

    from rf_propagation.hashing import compute_input_hash
    from rf_propagation.payload import build_request

    owner = create_user()
    node = create_observed_node(
        node_id=812_812_815,
        node_id_str=meshtastic_id_to_hex(812_812_815),
        claimed_by=owner,
    )
    profile = NodeRfProfile.objects.create(observed_node=node, **_rf_profile_fields())

    with tempfile.TemporaryDirectory() as tmp:
        settings.RF_PROPAGATION_ASSET_DIR = tmp
        payload = build_request(profile)
        input_hash = compute_input_hash(profile, extras={"radius_m": int(payload["radius"])})
        Path(tmp, f"{input_hash}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        NodeRfPropagationRender.objects.create(
            observed_node=node,
            status=NodeRfPropagationRender.Status.READY,
            input_hash=input_hash,
            asset_filename=f"{input_hash}.png",
            bounds_west=-5.0,
            bounds_south=55.0,
            bounds_east=-3.5,
            bounds_north=56.5,
        )

        client = APIClient()
        client.force_authenticate(user=owner)
        url = reverse("observed-node-rf-propagation-recompute", kwargs={"node_id": node.node_id})
        response = client.post(url, {}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "ready"
    assert response.data["input_hash"] == input_hash
    assert response.data["asset_url"] is not None
    stub_render_task.assert_not_called()


@pytest.mark.django_db
def test_rf_propagation_cancel_marks_in_flight_as_failed(create_observed_node, create_user, stub_render_task):
    owner = create_user()
    node = create_observed_node(
        node_id=812_812_816,
        node_id_str=meshtastic_id_to_hex(812_812_816),
        claimed_by=owner,
    )
    NodeRfProfile.objects.create(observed_node=node, **_rf_profile_fields())
    client = APIClient()
    client.force_authenticate(user=owner)

    recompute_url = reverse("observed-node-rf-propagation-recompute", kwargs={"node_id": node.node_id})
    cancel_url = reverse("observed-node-rf-propagation-cancel", kwargs={"node_id": node.node_id})

    client.post(recompute_url, {}, format="json")
    assert (
        NodeRfPropagationRender.objects.filter(
            observed_node=node,
            status=NodeRfPropagationRender.Status.PENDING,
        ).count()
        == 1
    )

    response = client.post(cancel_url, {}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["cancelled"] == 1

    row = NodeRfPropagationRender.objects.get(observed_node=node)
    assert row.status == NodeRfPropagationRender.Status.FAILED
    assert row.error_message == "Cancelled by user"
    assert row.completed_at is not None


@pytest.mark.django_db
def test_rf_propagation_cancel_is_noop_when_nothing_in_flight(create_observed_node, create_user):
    owner = create_user()
    node = create_observed_node(
        node_id=812_812_817,
        node_id_str=meshtastic_id_to_hex(812_812_817),
        claimed_by=owner,
    )
    client = APIClient()
    client.force_authenticate(user=owner)
    cancel_url = reverse("observed-node-rf-propagation-cancel", kwargs={"node_id": node.node_id})

    response = client.post(cancel_url, {}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["cancelled"] == 0


@pytest.mark.django_db
def test_rf_propagation_cancel_allows_new_recompute(create_observed_node, create_user, stub_render_task):
    owner = create_user()
    node = create_observed_node(
        node_id=812_812_818,
        node_id_str=meshtastic_id_to_hex(812_812_818),
        claimed_by=owner,
    )
    NodeRfProfile.objects.create(observed_node=node, **_rf_profile_fields())
    client = APIClient()
    client.force_authenticate(user=owner)
    recompute_url = reverse("observed-node-rf-propagation-recompute", kwargs={"node_id": node.node_id})
    cancel_url = reverse("observed-node-rf-propagation-cancel", kwargs={"node_id": node.node_id})

    first = client.post(recompute_url, {}, format="json")
    assert first.status_code == status.HTTP_201_CREATED
    client.post(cancel_url, {}, format="json")
    second = client.post(recompute_url, {}, format="json")

    assert second.status_code == status.HTTP_201_CREATED
    # First row cancelled, second row freshly dispatched → 2 rows + 2 .delay() calls.
    assert NodeRfPropagationRender.objects.filter(observed_node=node).count() == 2
    assert stub_render_task.call_count == 2


@pytest.mark.django_db
def test_rf_propagation_delete_removes_non_ready_rows(create_observed_node, create_user):
    owner = create_user()
    node = create_observed_node(
        node_id=812_812_820,
        node_id_str=meshtastic_id_to_hex(812_812_820),
        claimed_by=owner,
    )
    NodeRfPropagationRender.objects.create(observed_node=node, status=NodeRfPropagationRender.Status.PENDING)
    NodeRfPropagationRender.objects.create(
        observed_node=node,
        status=NodeRfPropagationRender.Status.FAILED,
        error_message="boom",
    )
    ready = NodeRfPropagationRender.objects.create(
        observed_node=node,
        status=NodeRfPropagationRender.Status.READY,
        asset_filename="h.png",
    )

    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("observed-node-rf-propagation-dismiss", kwargs={"node_id": node.node_id})
    response = client.post(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["deleted"] == 2
    # Only the ready row survives.
    remaining = list(NodeRfPropagationRender.objects.filter(observed_node=node))
    assert remaining == [ready]


@pytest.mark.django_db
def test_rf_propagation_delete_requires_edit_permission(create_observed_node, create_user):
    owner = create_user()
    stranger = create_user(username="stranger", email="stranger@example.com")
    node = create_observed_node(
        node_id=812_812_821,
        node_id_str=meshtastic_id_to_hex(812_812_821),
        claimed_by=owner,
    )
    NodeRfPropagationRender.objects.create(observed_node=node, status=NodeRfPropagationRender.Status.PENDING)
    client = APIClient()
    client.force_authenticate(user=stranger)
    url = reverse("observed-node-rf-propagation-dismiss", kwargs={"node_id": node.node_id})
    response = client.post(url)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert NodeRfPropagationRender.objects.filter(observed_node=node).count() == 1


@pytest.mark.django_db
def test_observed_node_detail_rf_flags(create_observed_node, create_user):
    owner = create_user()
    node = create_observed_node(
        node_id=813_813_813,
        node_id_str=meshtastic_id_to_hex(813_813_813),
        claimed_by=owner,
    )
    NodeRfProfile.objects.create(observed_node=node, antenna_pattern=AntennaPattern.OMNI)
    NodeRfPropagationRender.objects.create(
        observed_node=node,
        status=NodeRfPropagationRender.Status.READY,
        asset_filename="h.png",
    )
    client = APIClient()
    client.force_authenticate(user=owner)
    r = client.get(reverse("observed-node-detail", kwargs={"node_id": node.node_id}))
    assert r.status_code == status.HTTP_200_OK
    assert r.data["has_rf_profile"] is True
    assert r.data["has_ready_rf_render"] is True
    assert r.data["rf_profile_editable"] is True


@pytest.mark.django_db
def test_rf_propagation_asset_missing_file_404(settings, create_observed_node):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        settings.RF_PROPAGATION_ASSET_DIR = tmp
        node = create_observed_node(
            node_id=814_814_814,
            node_id_str=meshtastic_id_to_hex(814_814_814),
        )
        client = APIClient()
        url = reverse("rf-propagation-asset", kwargs={"node_id": node.node_id, "filename": "missing.png"})
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_rf_propagation_asset_serves_png_and_cache_control(settings, create_observed_node):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        settings.RF_PROPAGATION_ASSET_DIR = tmp
        Path(tmp, "tile.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        node = create_observed_node(
            node_id=815_815_815,
            node_id_str=meshtastic_id_to_hex(815_815_815),
        )
        client = APIClient()
        url = reverse("rf-propagation-asset", kwargs={"node_id": node.node_id, "filename": "tile.png"})
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/png"
        assert response["Cache-Control"] == "public, max-age=31536000, immutable"


@pytest.mark.django_db
def test_rf_propagation_asset_rejects_traversal(create_observed_node):
    node = create_observed_node(
        node_id=816_816_816,
        node_id_str=meshtastic_id_to_hex(816_816_816),
    )
    client = APIClient()
    url = reverse("rf-propagation-asset", kwargs={"node_id": node.node_id, "filename": "bad..name.png"})
    response = client.get(url)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
