"""Factory fixtures for traceroute_analytics tests."""

import pytest

import nodes.tests.conftest  # noqa: F401 - create_managed_node, etc.
import users.tests.conftest  # noqa: F401 - create_user
from traceroute.tests.factories import make_auto_traceroute


@pytest.fixture
def create_auto_traceroute(create_managed_node, create_observed_node, create_user):
    def _create(**kwargs):
        return make_auto_traceroute(
            create_managed_node,
            create_observed_node,
            create_user,
            **kwargs,
        )

    return _create
