from django.contrib.auth.models import Group

import pytest
from rest_framework.test import APIRequestFactory

from common.access import FEEDER_GROUP_NAME, AccessLevel, get_access_level, grant_feeder_role, user_is_feeder
from users.models import User


@pytest.mark.django_db
def test_grant_feeder_role():
    user = User.objects.create_user(username="feeder-user", password="x")
    assert not user_is_feeder(user)
    grant_feeder_role(user)
    assert user_is_feeder(user)
    assert Group.objects.filter(name=FEEDER_GROUP_NAME).exists()


@pytest.mark.django_db
def test_get_access_level_guest():
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = None
    assert get_access_level(request) == AccessLevel.GUEST


@pytest.mark.django_db
def test_get_access_level_feeder(create_user):
    user = create_user()
    grant_feeder_role(user)
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = user
    assert get_access_level(request) == AccessLevel.FEEDER


@pytest.mark.django_db
def test_get_access_level_admin(admin_user):
    factory = APIRequestFactory()
    request = factory.get("/")
    request.user = admin_user
    assert get_access_level(request) == AccessLevel.ADMIN
