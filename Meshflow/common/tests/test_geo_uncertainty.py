import pytest

from common.geo import position_uncertainty_km


@pytest.mark.parametrize(
    "bits,expected",
    [(15, 0.73), (13, 2.9), (10, 23.3), (9, 46.7)],
)
def test_position_uncertainty_km_worked_values(bits, expected):
    assert position_uncertainty_km(bits) == pytest.approx(expected, rel=0.02)


@pytest.mark.parametrize("bits", [None, 0, 32, 40])
def test_position_uncertainty_km_unknown_precision_is_zero(bits):
    assert position_uncertainty_km(bits) == 0.0
