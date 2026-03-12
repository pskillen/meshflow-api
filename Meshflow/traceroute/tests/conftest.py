import pytest

import nodes.tests.conftest  # noqa: F401 - load fixtures
import users.tests.conftest  # noqa: F401 - load fixtures
from traceroute.models import AutoTraceRoute


@pytest.fixture
def create_auto_traceroute(create_managed_node, create_observed_node, create_user):
    def make_auto_traceroute(**kwargs):
        if "source_node" not in kwargs:
            kwargs["source_node"] = create_managed_node()
        if "target_node" not in kwargs:
            kwargs["target_node"] = create_observed_node()
        if "trigger_type" not in kwargs:
            kwargs["trigger_type"] = AutoTraceRoute.TRIGGER_TYPE_USER
        if "triggered_by" not in kwargs:
            kwargs["triggered_by"] = create_user()
        if "status" not in kwargs:
            kwargs["status"] = AutoTraceRoute.STATUS_COMPLETED
        return AutoTraceRoute.objects.create(**kwargs)

    return make_auto_traceroute
