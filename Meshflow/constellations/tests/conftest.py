import pytest
from constellations.models import Constellation, ConstellationUserMembership
from users.tests.conftest import create_user, user_data


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
        if "owner" in data:  # Handle legacy owner parameter
            data["created_by"] = data.pop("owner")
        if "created_by" not in data:
            data["created_by"] = create_user()
        
        # Create the constellation
        constellation = Constellation.objects.create(**data)
        
        # Create admin membership for the creator
        ConstellationUserMembership.objects.create(
            user=data["created_by"],
            constellation=constellation,
            role="admin"
        )
        
        constellation.refresh_from_db()
        
        return constellation
    return make_constellation 