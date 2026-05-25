"""
ASGI helpers for quiet client disconnects (tab close, navigation, aborted fetch).

When a client goes away, uvicorn/Django cancel in-flight work with asyncio.CancelledError.
That is expected, not a server bug. We log a short warning and avoid ERROR tracebacks.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_AsyncioExceptionHandler = Callable[[asyncio.AbstractEventLoop, dict[str, Any]], None]
_previous_asyncio_handler: _AsyncioExceptionHandler | None = None
_asyncio_handler_installed = False


def install_asyncio_client_disconnect_handler() -> None:
    """Route asyncio CancelledError reports to a warning instead of default ERROR + traceback."""
    global _previous_asyncio_handler, _asyncio_handler_installed
    if _asyncio_handler_installed:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return

    _previous_asyncio_handler = loop.get_exception_handler()

    def handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exc = context.get("exception")
        if isinstance(exc, asyncio.CancelledError):
            message = context.get("message", "async task cancelled")
            logger.warning("Client disconnected (%s)", message)
            return
        if _previous_asyncio_handler is not None:
            _previous_asyncio_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(handler)
    _asyncio_handler_installed = True


def log_client_disconnect(scope: dict[str, Any]) -> None:
    conn_type = scope.get("type", "unknown")
    path = scope.get("path", "")
    if conn_type == "websocket":
        logger.warning("WebSocket client disconnected: %s", path)
    else:
        logger.warning("HTTP client disconnected during request: %s", path)


class ClientDisconnectLogFilter(logging.Filter):
    """Downgrade asyncio CancelledError log records to warnings without exc_info."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "CancelledError" in message and "shielded future" in message:
            record.levelno = logging.WARNING
            record.levelname = "WARNING"
            record.exc_info = None
            record.exc_text = None

        if record.exc_info and record.exc_info[0] is asyncio.CancelledError:
            record.levelno = logging.WARNING
            record.levelname = "WARNING"
            record.exc_info = None
            record.exc_text = None

        return True


class ClientDisconnectLoggingMiddleware:
    """ASGI middleware: expected client disconnects -> warning, then re-raise CancelledError."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        install_asyncio_client_disconnect_handler()
        try:
            await self.app(scope, receive, send)
        except asyncio.CancelledError:
            log_client_disconnect(scope)
            raise
