import pytest

from constellations.models import Constellation
from users.tests.conftest import create_user, user_data  # noqa F401


@pytest.fixture
def constellation_data():
    return {
        "name": "Test Constellation",
        "description": "Test Description",
    }


@pytest.fixture
def create_constellation(create_user, constellation_data):  # noqa: F811
    def make_constellation(**kwargs):
        data = constellation_data.copy()
        data.update(kwargs)
        if "owner" in data:
            data["created_by"] = data.pop("owner")
        if "created_by" not in data:
            data["created_by"] = create_user()

        constellation = Constellation.objects.create(**data)
        constellation.refresh_from_db()
        return constellation

    return make_constellation
