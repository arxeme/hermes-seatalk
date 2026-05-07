from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable
from unittest.mock import MagicMock

from aiohttp import web
import pytest

from hermes_seatalk.relay import SeaTalkRelayClient, _apply_tcp_keepalive


async def _noop_sleep(_delay):
    await asyncio.sleep(0)


async def _start_ws_server(handler: Callable[[web.WebSocketResponse], Awaitable[None]]):
    async def ws_handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await handler(ws)
        return ws

    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets  # type: ignore[union-attr]
    host, port = sockets[0].getsockname()[:2]
    return runner, f"http://{host}:{port}/ws"


def _client(url, dispatch, **kwargs):
    return SeaTalkRelayClient(
        relay_url=url,
        app_id="app-id",
        app_secret="app-secret",
        signing_secret="signing-secret",
        dispatch=dispatch,
        reconnect_initial_seconds=kwargs.pop("reconnect_initial_seconds", 0),
        reconnect_max_seconds=kwargs.pop("reconnect_max_seconds", 0),
        sleep_fn=kwargs.pop("sleep_fn", _noop_sleep),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_t05_01_relay_connect_success():
    ready = asyncio.Event()
    release = asyncio.Event()

    async def handler(ws):
        auth = await ws.receive_json()
        assert auth["type"] == "auth"
        await ws.send_json({"type": "auth_ok"})
        ready.set()
        await release.wait()

    runner, url = await _start_ws_server(handler)
    client = _client(url, lambda _event, _source: None)
    try:
        assert await client.start(timeout=1) is True
        assert client.connected.is_set() is True
        await asyncio.wait_for(ready.wait(), timeout=1)
    finally:
        release.set()
        await client.stop()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_t05_02_relay_message_dispatch():
    received = []
    dispatched = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(event, source):
        received.append((event, source))
        dispatched.set()

    async def handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await ws.send_json({"type": "event", "event": {"event_type": "message_from_bot_subscriber"}})
        await release.wait()

    runner, url = await _start_ws_server(handler)
    client = _client(url, dispatch)
    try:
        assert await client.start(timeout=1) is True
        await asyncio.wait_for(dispatched.wait(), timeout=1)
        assert received == [({"event_type": "message_from_bot_subscriber"}, "relay")]
    finally:
        release.set()
        await client.stop()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_t05_03_relay_malformed_does_not_crash():
    got_pong = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(_event, _source):
        raise AssertionError("malformed JSON must not dispatch")

    async def handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await ws.send_str("{bad-json")
        await ws.send_json({"type": "ping"})
        msg = await ws.receive_json()
        if msg == {"type": "pong"}:
            got_pong.set()
        await release.wait()

    runner, url = await _start_ws_server(handler)
    client = _client(url, dispatch)
    try:
        assert await client.start(timeout=1) is True
        await asyncio.wait_for(got_pong.wait(), timeout=1)
        assert client.connected.is_set() is True
    finally:
        release.set()
        await client.stop()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_t05_04_reconnect_after_disconnect():
    count = 0
    second = asyncio.Event()
    release = asyncio.Event()

    async def handler(ws):
        nonlocal count
        count += 1
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        if count == 1:
            await ws.close()
        else:
            second.set()
            await release.wait()

    runner, url = await _start_ws_server(handler)
    client = _client(url, lambda _event, _source: None)
    try:
        assert await client.start(timeout=1) is True
        await asyncio.wait_for(second.wait(), timeout=1)
        assert count >= 2
    finally:
        release.set()
        await client.stop()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_t05_05_heartbeat_timeout_marks_state():
    release = asyncio.Event()

    async def handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await release.wait()

    runner, url = await _start_ws_server(handler)
    client = _client(
        url,
        lambda _event, _source: None,
        heartbeat_timeout_seconds=0.05,
        reconnect_initial_seconds=60,
        reconnect_max_seconds=60,
        sleep_fn=asyncio.sleep,
    )
    try:
        assert await client.start(timeout=1) is True
        for _ in range(30):
            if client.last_error == "heartbeat timeout":
                break
            await asyncio.sleep(0.01)
        assert client.last_error == "heartbeat timeout"
    finally:
        release.set()
        await client.stop()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_t05_06_shutdown_exits_relay_client():
    release = asyncio.Event()

    async def handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await release.wait()

    runner, url = await _start_ws_server(handler)
    client = _client(url, lambda _event, _source: None)
    try:
        assert await client.start(timeout=1) is True
        release.set()
        await client.stop()
        assert client._task is None
        assert client.connected.is_set() is False
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_t05_07_replaced_triggers_reconnect():
    """replaced message must not set auth_failed; client reconnects after backoff."""
    count = 0
    second_auth = asyncio.Event()
    release = asyncio.Event()

    async def handler(ws):
        nonlocal count
        count += 1
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        if count == 1:
            await ws.send_json({"type": "replaced"})
        else:
            second_auth.set()
            await release.wait()

    runner, url = await _start_ws_server(handler)
    client = _client(url, lambda _event, _source: None)
    try:
        assert await client.start(timeout=1) is True
        await asyncio.wait_for(second_auth.wait(), timeout=2)
        assert count >= 2
        assert client.auth_failed is False
    finally:
        release.set()
        await client.stop()
        await runner.cleanup()


def test_t05_08_tcp_keepalive_applied_to_socket():
    """_apply_tcp_keepalive sets SO_KEEPALIVE on the underlying socket."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        mock_ws = MagicMock()
        mock_ws._conn.transport.get_extra_info.return_value = sock

        _apply_tcp_keepalive(mock_ws, idle_seconds=60)

        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) != 0
    finally:
        sock.close()


def test_t05_09_tcp_keepalive_silent_on_missing_transport():
    """_apply_tcp_keepalive does not raise when transport has no socket."""
    mock_ws = MagicMock()
    mock_ws._conn.transport.get_extra_info.return_value = None
    _apply_tcp_keepalive(mock_ws)  # must not raise


def test_t05_10_tcp_keepalive_silent_on_broken_transport():
    """_apply_tcp_keepalive does not raise when _conn is inaccessible."""
    mock_ws = MagicMock()
    mock_ws._conn.transport.get_extra_info.side_effect = AttributeError("no transport")
    _apply_tcp_keepalive(mock_ws)  # must not raise
