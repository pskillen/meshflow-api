from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("name", ["openapi.yaml", "openapi-m2m.yaml"])
def test_openapi_parses_as_strict_yaml(name):
    doc = yaml.safe_load((REPO_ROOT / name).read_text())
    assert doc["openapi"].startswith("3.")
