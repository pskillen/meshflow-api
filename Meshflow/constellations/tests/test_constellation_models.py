import pytest

from constellations.models import Constellation  # noqa: F401


@pytest.mark.django_db
def test_constellation_str(create_constellation):
    constellation = create_constellation(name="Alpha")
    assert str(constellation) == "Alpha"
