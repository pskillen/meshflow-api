import pytest

from nodes.models import NodeLatestStatus

pytest_plugins = [
    "users.tests.conftest",
    "nodes.tests.conftest",
    "constellations.tests.conftest",
]


@pytest.fixture
def observed_node_with_position(create_observed_node):
    node = create_observed_node()
    NodeLatestStatus.objects.update_or_create(
        node=node,
        defaults={
            "latitude": 55.95,
            "longitude": -3.19,
            "altitude": 100,
            "position_reported_time": None,
        },
    )
    node.refresh_from_db()
    return node
