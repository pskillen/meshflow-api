import pytest

import nodes.tests.conftest  # noqa: F401 - load fixtures
import users.tests.conftest  # noqa: F401 - load fixtures
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
