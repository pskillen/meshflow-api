from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from common.protocol import Protocol
from constellations.models import Constellation, MessageChannel


@pytest.mark.django_db
def test_guest_can_list_all_constellations(create_constellation, create_user):
    client = APIClient()
    create_constellation(created_by=create_user(), name="A")
    create_constellation(created_by=create_user(), name="B")

    response = client.get(reverse("constellation-list"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 2


@pytest.mark.django_db
def test_authenticated_user_sees_all_constellations_without_membership(create_constellation, create_user):
    client = APIClient()
    owner = create_user()
    other = create_user()
    create_constellation(created_by=owner, name="Owner region")
    client.force_authenticate(user=other)

    response = client.get(reverse("constellation-list"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_constellation_list_protocol_filter(create_constellation, create_user):
    client = APIClient()
    user = create_user()
    client.force_authenticate(user=user)

    mt = create_constellation(created_by=user, name="MT Only", protocol=Protocol.MESHTASTIC)
    mc = create_constellation(created_by=user, name="MC Only", protocol=Protocol.MESHCORE)
    MessageChannel.objects.create(
        name="MC Ch",
        constellation=mc,
        protocol=Protocol.MESHCORE,
        mc_channel_idx=1,
    )

    response = client.get(reverse("constellation-list"), {"protocol": "meshcore"})

    assert response.status_code == status.HTTP_200_OK
    ids = {row["id"] for row in response.data["results"]}
    assert ids == {mc.id}


@pytest.mark.django_db
def test_guest_can_retrieve_constellation(create_constellation, create_user):
    client = APIClient()
    constellation = create_constellation(created_by=create_user())

    response = client.get(reverse("constellation-detail", kwargs={"pk": constellation.pk}))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["name"] == constellation.name


@pytest.mark.django_db
def test_constellation_create_requires_staff(create_user):
    client = APIClient()
    user = create_user(is_staff=True)
    client.force_authenticate(user=user)

    response = client.post(
        reverse("constellation-list"),
        {"name": "New Constellation", "description": "New Description"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert Constellation.objects.count() == 1


@pytest.mark.django_db
def test_constellation_create_denied_for_non_staff(create_user):
    client = APIClient()
    client.force_authenticate(user=create_user(is_staff=False))

    response = client.post(
        reverse("constellation-list"),
        {"name": "New Constellation", "description": "x"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_constellation_update_requires_staff(create_constellation, create_user):
    client = APIClient()
    constellation = create_constellation()
    client.force_authenticate(user=create_user(is_staff=True))

    response = client.patch(
        reverse("constellation-detail", kwargs={"pk": constellation.pk}),
        {"name": "Updated"},
    )

    assert response.status_code == status.HTTP_200_OK
    constellation.refresh_from_db()
    assert constellation.name == "Updated"


@pytest.mark.django_db
def test_guest_can_list_channels(create_constellation, create_user):
    client = APIClient()
    constellation = create_constellation(created_by=create_user(), protocol=Protocol.MESHCORE)
    MessageChannel.objects.create(
        name="MC",
        constellation=constellation,
        protocol=Protocol.MESHCORE,
        mc_channel_idx=0,
    )

    url = reverse("constellation-channels-list-create", kwargs={"constellation_id": constellation.id})
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
