"""Unit tests for :mod:`rf_propagation.client`.

We mock the HTTP layer with :mod:`respx` so we can exercise the error-mapping
logic without touching the real engine.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from rf_propagation.client import (
    EngineFatalError,
    EngineTransientError,
    SitePlannerClient,
)

BASE_URL = "http://site-planner.test:8080"


@respx.mock
def test_submit_returns_task_id():
    route = respx.post(f"{BASE_URL}/predict").mock(
        return_value=httpx.Response(200, json={"task_id": "abc-123"}),
    )
    with SitePlannerClient(BASE_URL) as client:
        result = client.submit({"tx_lat": 0.0})
    assert route.called
    assert result.task_id == "abc-123"


@respx.mock
def test_submit_accepts_id_alias():
    respx.post(f"{BASE_URL}/predict").mock(return_value=httpx.Response(200, json={"id": "xyz"}))
    with SitePlannerClient(BASE_URL) as client:
        assert client.submit({}).task_id == "xyz"


@respx.mock
def test_submit_5xx_is_transient():
    respx.post(f"{BASE_URL}/predict").mock(return_value=httpx.Response(503, text="overloaded"))
    with SitePlannerClient(BASE_URL) as client:
        with pytest.raises(EngineTransientError):
            client.submit({})


@respx.mock
def test_submit_4xx_is_fatal():
    respx.post(f"{BASE_URL}/predict").mock(return_value=httpx.Response(400, text="bad payload"))
    with SitePlannerClient(BASE_URL) as client:
        with pytest.raises(EngineFatalError):
            client.submit({})


@respx.mock
def test_status_parses_lowercase():
    respx.get(f"{BASE_URL}/status/42").mock(return_value=httpx.Response(200, json={"status": "DONE"}))
    with SitePlannerClient(BASE_URL) as client:
        assert client.status("42") == "done"


@respx.mock
def test_result_returns_raw_bytes():
    tiff_bytes = b"II*\x00...synthetic geotiff..."
    respx.get(f"{BASE_URL}/result/42").mock(return_value=httpx.Response(200, content=tiff_bytes))
    with SitePlannerClient(BASE_URL) as client:
        assert client.result("42") == tiff_bytes


@respx.mock
def test_result_empty_body_is_fatal():
    respx.get(f"{BASE_URL}/result/42").mock(return_value=httpx.Response(200, content=b""))
    with SitePlannerClient(BASE_URL) as client:
        with pytest.raises(EngineFatalError):
            client.result("42")


@respx.mock
def test_transport_error_mapped_to_transient():
    respx.post(f"{BASE_URL}/predict").mock(side_effect=httpx.ConnectError("boom"))
    with SitePlannerClient(BASE_URL) as client:
        with pytest.raises(EngineTransientError):
            client.submit({})


def test_requires_base_url():
    with pytest.raises(ValueError):
        SitePlannerClient("")


@respx.mock
def test_submit_non_json_is_fatal():
    respx.post(f"{BASE_URL}/predict").mock(return_value=httpx.Response(200, content=b"<html></html>"))
    with SitePlannerClient(BASE_URL) as client:
        with pytest.raises(EngineFatalError):
            client.submit({})
