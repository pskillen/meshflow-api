"""Route compatibility: analytics endpoints stay under ``/api/traceroutes/``."""

from django.urls import resolve

import pytest


@pytest.mark.parametrize(
    "suffix,url_name",
    [
        ("stats/", "traceroute-stats"),
        ("heatmap-edges/", "traceroute-heatmap-edges"),
        ("feeder-reach/", "traceroute-feeder-reach"),
        ("constellation-coverage/", "traceroute-constellation-coverage"),
    ],
)
def test_analytics_paths_resolve(suffix, url_name):
    match = resolve(f"/api/traceroutes/{suffix}")
    assert match.url_name == url_name
