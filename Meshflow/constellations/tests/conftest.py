import pytest
from constellations.models import Constellation
from users.tests.conftest import create_user


@pytest.fixture
def constellation_data():
    return {
        "name": "Test Constellation",
        "description": "Test Description",
    }


@pytest.fixture
def create_constellation(create_user, constellation_data):
    def make_constellation(**kwargs):
        data = constellation_data.copy()
        data.update(kwargs)
        if "owner" not in data:
            data["owner"] = create_user()
        return Constellation.objects.create(**data)
    return make_constellation 