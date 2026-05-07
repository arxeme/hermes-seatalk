from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace

from aiohttp import web
import pytest

from hermes_seatalk import adapter


class FakeClient:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class FakeDispatcher:
    def __init__(self):
        self.events = []

    async def dispatch(self, event, source):
        self.events.append((event, source))

    async def flush_all(self):
        return None


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


def _config(**extra):
    return SimpleNamespace(enabled=True, extra=extra)


def _relay_account(app_id, relay_url, **overrides):
    account = {
        "enabled": True,
        "app_id": app_id,
        "app_secret": f"{app_id}-secret",
        "signing_secret": f"{app_id}-signing",
        "mode": "relay",
        "relay_url": relay_url,
    }
    account.update(overrides)
    return account


def _adapter(default_url, staging_url, default_dispatcher=None, staging_dispatcher=None):
    return adapter.SeaTalkAdapter(_config(
        accounts={
            "default": _relay_account("app-default", default_url),
            "staging": _relay_account("app-staging", staging_url),
        },
        clients={
            "default": FakeClient(),
            "staging": FakeClient(),
        },
        dispatchers={
            "default": default_dispatcher or FakeDispatcher(),
            "staging": staging_dispatcher or FakeDispatcher(),
        },
        relay_connect_timeout_seconds=0.1,
        relay_heartbeat_timeout_seconds=0.05,
        relay_state_poll_seconds=0.01,
        relay_reconnect_initial_seconds=60,
        relay_reconnect_max_seconds=60,
    ))


async def _wait_for_state(seatalk, account_id, state):
    for _ in range(100):
        if seatalk._runtimes[account_id].state == state:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"{account_id} did not reach state {state}")


@pytest.mark.asyncio
async def test_t2_04_01_multi_relay_startup():
    releases = [asyncio.Event(), asyncio.Event()]

    async def handler_factory(index):
        async def handler(ws):
            await ws.receive_json()
            await ws.send_json({"type": "auth_ok"})
            await releases[index].wait()
        return handler

    runner_default, default_url = await _start_ws_server(await handler_factory(0))
    runner_staging, staging_url = await _start_ws_server(await handler_factory(1))
    seatalk = _adapter(default_url, staging_url)
    try:
        assert await seatalk.connect() is True
        assert seatalk._runtimes["default"].state == "running"
        assert seatalk._runtimes["staging"].state == "running"
    finally:
        for release in releases:
            release.set()
        await seatalk.disconnect()
        await runner_default.cleanup()
        await runner_staging.cleanup()


@pytest.mark.asyncio
async def test_t2_04_02_relay_event_routes_to_account_dispatcher():
    default_dispatcher = FakeDispatcher()
    staging_dispatcher = FakeDispatcher()
    releases = [asyncio.Event(), asyncio.Event()]
    dispatched = asyncio.Event()

    async def default_handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await ws.send_json({"type": "event", "event": {"app_id": "app-default", "event_type": "unknown_default"}})
        await releases[0].wait()

    async def staging_handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await ws.send_json({"type": "event", "event": {"app_id": "app-staging", "event_type": "unknown_staging"}})
        dispatched.set()
        await releases[1].wait()

    runner_default, default_url = await _start_ws_server(default_handler)
    runner_staging, staging_url = await _start_ws_server(staging_handler)
    seatalk = _adapter(default_url, staging_url, default_dispatcher, staging_dispatcher)
    try:
        assert await seatalk.connect() is True
        await asyncio.wait_for(dispatched.wait(), timeout=1)
        for _ in range(20):
            if default_dispatcher.events and staging_dispatcher.events:
                break
            await asyncio.sleep(0.01)
        assert default_dispatcher.events == [({"app_id": "app-default", "event_type": "unknown_default"}, "relay")]
        assert staging_dispatcher.events == [({"app_id": "app-staging", "event_type": "unknown_staging"}, "relay")]
    finally:
        for release in releases:
            release.set()
        await seatalk.disconnect()
        await runner_default.cleanup()
        await runner_staging.cleanup()


@pytest.mark.asyncio
async def test_t2_04_03_relay_payload_app_id_mismatch(caplog):
    default_dispatcher = FakeDispatcher()
    seatalk = _adapter("http://127.0.0.1:1/ws", "http://127.0.0.1:2/ws", default_dispatcher)

    with caplog.at_level("WARNING", logger="hermes_seatalk.adapter"):
        await seatalk._dispatch_runtime_event(
            "default",
            {"app_id": "app-other", "event_type": "message_from_bot_subscriber"},
            "relay",
        )

    assert default_dispatcher.events == []
    assert "app_id_mismatch" in caplog.text
    assert "account_id=default" in caplog.text


@pytest.mark.asyncio
async def test_t2_04_04_auth_fail_isolated():
    release = asyncio.Event()

    async def auth_fail_handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_fail", "error": "bad credentials"})

    async def ok_handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await release.wait()

    runner_default, default_url = await _start_ws_server(auth_fail_handler)
    runner_staging, staging_url = await _start_ws_server(ok_handler)
    seatalk = _adapter(default_url, staging_url)
    try:
        assert await seatalk.connect() is True
        assert seatalk._runtimes["default"].state == "auth_failed"
        assert seatalk._runtimes["staging"].state == "running"
    finally:
        release.set()
        await seatalk.disconnect()
        await runner_default.cleanup()
        await runner_staging.cleanup()


@pytest.mark.asyncio
async def test_t2_04_05_network_failure_isolated_as_retrying():
    release = asyncio.Event()

    async def no_auth_handler(ws):
        await ws.receive_json()
        await release.wait()

    async def ok_handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await release.wait()

    runner_default, default_url = await _start_ws_server(no_auth_handler)
    runner_staging, staging_url = await _start_ws_server(ok_handler)
    seatalk = _adapter(default_url, staging_url)
    try:
        assert await seatalk._connect_runtime(seatalk._runtimes["default"]) is True
        assert await seatalk._connect_runtime(seatalk._runtimes["staging"]) is True
        assert seatalk._runtimes["default"].state == "retrying"
        assert seatalk._runtimes["staging"].state == "running"
    finally:
        release.set()
        await seatalk.disconnect()
        await runner_default.cleanup()
        await runner_staging.cleanup()


@pytest.mark.asyncio
async def test_t2_04_06_replaced_triggers_reconnect_not_auth_failed():
    """replaced must not set auth_failed; client reconnects and staging is unaffected."""
    release = asyncio.Event()
    reconnected = asyncio.Event()

    attempt = 0

    async def replaced_handler(ws):
        nonlocal attempt
        attempt += 1
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        if attempt == 1:
            await ws.send_json({"type": "replaced"})
        else:
            reconnected.set()
            await release.wait()

    async def ok_handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await release.wait()

    runner_default, default_url = await _start_ws_server(replaced_handler)
    runner_staging, staging_url = await _start_ws_server(ok_handler)
    # Use fast reconnect so the test doesn't wait 60s for the retry
    seatalk = adapter.SeaTalkAdapter(_config(
        accounts={
            "default": _relay_account("app-default", default_url),
            "staging": _relay_account("app-staging", staging_url),
        },
        clients={"default": FakeClient(), "staging": FakeClient()},
        dispatchers={"default": FakeDispatcher(), "staging": FakeDispatcher()},
        relay_connect_timeout_seconds=0.1,
        relay_heartbeat_timeout_seconds=0.05,
        relay_state_poll_seconds=0.01,
        relay_reconnect_initial_seconds=0,
        relay_reconnect_max_seconds=0,
    ))
    try:
        assert await seatalk.connect() is True
        # Client must reconnect after replaced, not enter auth_failed
        await asyncio.wait_for(reconnected.wait(), timeout=2)
        assert seatalk._runtimes["default"].auth_failed is False
        assert seatalk._runtimes["staging"].state == "running"
    finally:
        release.set()
        await seatalk.disconnect()
        await runner_default.cleanup()
        await runner_staging.cleanup()


@pytest.mark.asyncio
async def test_t2_04_07_heartbeat_timeout_isolated_as_retrying():
    release = asyncio.Event()

    async def timeout_handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await release.wait()

    async def ok_handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await release.wait()

    runner_default, default_url = await _start_ws_server(timeout_handler)
    runner_staging, staging_url = await _start_ws_server(ok_handler)
    seatalk = _adapter(default_url, staging_url)
    try:
        assert await seatalk.connect() is True
        await _wait_for_state(seatalk, "default", "retrying")
        assert seatalk._runtimes["staging"].state == "running"
    finally:
        release.set()
        await seatalk.disconnect()
        await runner_default.cleanup()
        await runner_staging.cleanup()


@pytest.mark.asyncio
async def test_t2_04_08_network_disconnect_isolated_as_retrying():
    release = asyncio.Event()

    async def disconnect_handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await ws.close()

    async def ok_handler(ws):
        await ws.receive_json()
        await ws.send_json({"type": "auth_ok"})
        await release.wait()

    runner_default, default_url = await _start_ws_server(disconnect_handler)
    runner_staging, staging_url = await _start_ws_server(ok_handler)
    seatalk = _adapter(default_url, staging_url)
    try:
        assert await seatalk.connect() is True
        await _wait_for_state(seatalk, "default", "retrying")
        assert seatalk._runtimes["staging"].state == "running"
    finally:
        release.set()
        await seatalk.disconnect()
        await runner_default.cleanup()
        await runner_staging.cleanup()


def test_t2_04_09_relay_logs_include_account_id(caplog):
    seatalk = _adapter("http://127.0.0.1:1/ws", "http://127.0.0.1:2/ws")

    with caplog.at_level("INFO", logger="hermes_seatalk.adapter"):
        seatalk._set_runtime_state(seatalk._runtimes["staging"], "retrying", "network")

    assert "account_id=staging" in caplog.text
