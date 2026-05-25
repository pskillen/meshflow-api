import asyncio
import logging

import pytest

from Meshflow.asgi_client_disconnect import (
    ClientDisconnectLogFilter,
    ClientDisconnectLoggingMiddleware,
    install_asyncio_client_disconnect_handler,
    log_client_disconnect,
)


@pytest.mark.asyncio
async def test_middleware_logs_and_reraises_cancelled_error(caplog):
    caplog.set_level(logging.WARNING, logger="Meshflow.asgi_client_disconnect")

    async def inner_app(scope, receive, send):
        raise asyncio.CancelledError

    middleware = ClientDisconnectLoggingMiddleware(inner_app)

    with pytest.raises(asyncio.CancelledError):
        await middleware({"type": "websocket", "path": "/ws/traceroutes/"}, None, None)

    assert any("WebSocket client disconnected" in r.message for r in caplog.records)


def test_log_client_disconnect_http(caplog):
    caplog.set_level(logging.WARNING, logger="Meshflow.asgi_client_disconnect")
    log_client_disconnect({"type": "http", "path": "/api/nodes/"})
    assert any("HTTP client disconnected" in r.message for r in caplog.records)


def test_client_disconnect_log_filter_downgrades_asyncio_message():
    record = logging.LogRecord(
        name="asyncio",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="CancelledError exception in shielded future",
        args=(),
        exc_info=None,
    )
    assert ClientDisconnectLogFilter().filter(record) is True
    assert record.levelno == logging.WARNING
    assert record.exc_info is None


def test_install_asyncio_handler_suppresses_cancelled_error(caplog):
    caplog.set_level(logging.WARNING, logger="Meshflow.asgi_client_disconnect")

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        import Meshflow.asgi_client_disconnect as mod

        mod._asyncio_handler_installed = False
        install_asyncio_client_disconnect_handler()

        handler = loop.get_exception_handler()
        assert handler is not None
        handler(loop, {"message": "test cancel", "exception": asyncio.CancelledError()})
        assert any("Client disconnected" in r.message for r in caplog.records)
    finally:
        loop.close()
        import Meshflow.asgi_client_disconnect as mod

        mod._asyncio_handler_installed = False
