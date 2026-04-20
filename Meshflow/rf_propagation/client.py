"""Thin HTTP client for Meshtastic Site Planner.

We keep retries and polling cadence in the Celery task — this module only
shapes the three HTTP calls and exposes a couple of typed exceptions the
task can branch on (transient vs fatal).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class EngineError(RuntimeError):
    """Base class for Site Planner engine errors."""


class EngineTransientError(EngineError):
    """HTTP 5xx / connection reset / timeout — the Celery task should retry."""


class EngineFatalError(EngineError):
    """The engine rejected the request (4xx, reported ``failed``, bad body)."""


@dataclass(frozen=True)
class SubmitResponse:
    task_id: str


# Site Planner's OpenAPI schema calls this ``/predict``; the upstream
# pydantic docstring sometimes refers to ``/coverage``. We centralize the
# path here so fixing that becomes a one-line change.
PREDICT_PATH = "/predict"
STATUS_PATH_TMPL = "/status/{task_id}"
RESULT_PATH_TMPL = "/result/{task_id}"

DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT_SHORT = 30.0
DEFAULT_READ_TIMEOUT_RESULT = 120.0


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    if 500 <= response.status_code < 600:
        raise EngineTransientError(f"engine {response.status_code}: {response.text[:200]}")
    raise EngineFatalError(f"engine {response.status_code}: {response.text[:200]}")


class SitePlannerClient:
    """Synchronous httpx wrapper over the Site Planner coverage API."""

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout_short: float = DEFAULT_READ_TIMEOUT_SHORT,
        read_timeout_result: float = DEFAULT_READ_TIMEOUT_RESULT,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required (see RF_PROPAGATION_ENGINE_URL)")
        self._base_url = base_url.rstrip("/")
        self._owned_client = client is None
        self._client = client or httpx.Client(base_url=self._base_url)
        self._read_timeout_short = read_timeout_short
        self._read_timeout_result = read_timeout_result
        self._connect_timeout = connect_timeout

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    def __enter__(self) -> "SitePlannerClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # --- HTTP surface ---------------------------------------------------

    def submit(self, payload: dict[str, Any]) -> SubmitResponse:
        timeout = httpx.Timeout(self._read_timeout_short, connect=self._connect_timeout)
        try:
            response = self._client.post(PREDICT_PATH, json=payload, timeout=timeout)
        except httpx.TransportError as exc:
            raise EngineTransientError(f"transport error submitting: {exc}") from exc
        _raise_for_status(response)
        try:
            data = response.json()
        except ValueError as exc:
            raise EngineFatalError(f"engine returned non-JSON submit body: {exc}") from exc
        task_id = data.get("task_id") or data.get("id")
        if not task_id:
            raise EngineFatalError(f"engine submit response missing task_id: {data!r}")
        return SubmitResponse(task_id=str(task_id))

    def status(self, task_id: str) -> str:
        timeout = httpx.Timeout(self._read_timeout_short, connect=self._connect_timeout)
        path = STATUS_PATH_TMPL.format(task_id=task_id)
        try:
            response = self._client.get(path, timeout=timeout)
        except httpx.TransportError as exc:
            raise EngineTransientError(f"transport error polling status: {exc}") from exc
        _raise_for_status(response)
        try:
            data = response.json()
        except ValueError as exc:
            raise EngineFatalError(f"engine returned non-JSON status body: {exc}") from exc
        status_value = data.get("status")
        if not status_value:
            raise EngineFatalError(f"engine status response missing status: {data!r}")
        return str(status_value).lower()

    def result(self, task_id: str) -> bytes:
        timeout = httpx.Timeout(self._read_timeout_result, connect=self._connect_timeout)
        path = RESULT_PATH_TMPL.format(task_id=task_id)
        try:
            response = self._client.get(path, timeout=timeout)
        except httpx.TransportError as exc:
            raise EngineTransientError(f"transport error fetching result: {exc}") from exc
        _raise_for_status(response)
        if not response.content:
            raise EngineFatalError("engine returned empty result body")
        return response.content
