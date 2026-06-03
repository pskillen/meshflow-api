"""Tests for MeshCore region_scope normalization."""

import pytest

from common.mc_region_scope import normalize_region_scope


def test_normalize_region_scope_null_values():
    assert normalize_region_scope(None) is None
    assert normalize_region_scope("") is None
    assert normalize_region_scope("*") is None
    assert normalize_region_scope("none") is None
    assert normalize_region_scope("  *  ") is None


def test_normalize_region_scope_valid():
    assert normalize_region_scope("Sample-West") == "sample-west"
    assert normalize_region_scope("#galloway") == "galloway"


def test_normalize_region_scope_invalid():
    with pytest.raises(ValueError, match="alphanumeric"):
        normalize_region_scope("bad scope")
    with pytest.raises(ValueError, match="UTF-8"):
        normalize_region_scope("a" * 30)
