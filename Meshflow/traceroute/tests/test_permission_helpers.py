"""Tests for traceroute permission_helpers (feeder / admin model)."""

import pytest

import nodes.tests.conftest  # noqa: F401 - load fixtures
import users.tests.conftest  # noqa: F401 - load fixtures
from common.access import grant_feeder_role
from traceroute.permission_helpers import user_can_trigger_from_node


@pytest.fixture
def staff_user(create_user):
    user = create_user()
    user.is_staff = True
    user.save()
    return user


@pytest.fixture
def feeder_user(create_user):
    user = create_user()
    grant_feeder_role(user)
    return user


@pytest.fixture
def plain_user(create_user):
    return create_user()


@pytest.mark.django_db
class TestUserCanTriggerFromNode:
    def test_staff_can_trigger_from_eligible_node(self, staff_user, create_managed_node):
        mn = create_managed_node(allow_auto_traceroute=True)
        assert user_can_trigger_from_node(staff_user, mn) is True

    def test_feeder_can_trigger_from_any_eligible_node(self, feeder_user, create_managed_node):
        mn = create_managed_node(allow_auto_traceroute=True)
        assert user_can_trigger_from_node(feeder_user, mn) is True

    def test_plain_user_cannot_trigger(self, plain_user, create_managed_node):
        mn = create_managed_node(allow_auto_traceroute=True)
        assert user_can_trigger_from_node(plain_user, mn) is False

    def test_feeder_cannot_trigger_when_auto_disabled(self, feeder_user, create_managed_node):
        mn = create_managed_node(allow_auto_traceroute=False)
        assert user_can_trigger_from_node(feeder_user, mn) is False
