from __future__ import annotations

import asyncio
import hashlib
import json
import socket
from types import SimpleNamespace

import aiohttp
import pytest

from hermes_seatalk import adapter
from hermes_seatalk.webhook import SeaTalkWebhookAccount, SeaTalkWebhookServer


def _signature(body: bytes, secret: str) -> str:
    return hashlib.sha256(body + secret.encode("utf-8")).hexdigest()


async def _url(server: SeaTalkWebhookServer) -> str:
    sockets = server.site._server.sockets  # type: ignore[union-attr, attr-defined]
    host, port = sockets[0].getsockname()[:2]
    return f"http://{host}:{port}{server.path}"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeClient:
    async def close(self):
        return None


class FakeDispatcher:
    def __init__(self):
        self.events = []

    async def dispatch(self, event, source):
        self.events.append((event, source))

    async def flush_all(self):
        return None


def _webhook_account(app_id, **overrides):
    account = {
        "enabled": True,
        "app_id": app_id,
        "app_secret": f"{app_id}-secret",
        "signing_secret": f"{app_id}-signing",
        "mode": "webhook",
        "webhook_host": "127.0.0.1",
        "webhook_port": 8080,
        "webhook_path": "/callback",
    }
    account.update(overrides)
    return account


def _config(**extra):
    return SimpleNamespace(enabled=True, extra=extra)


async def _noop_dispatch(_event, _source):
    return None


def _server(default_dispatch=None, staging_dispatch=None):
    return SeaTalkWebhookServer(
        host="127.0.0.1",
        port=0,
        path="/callback",
        accounts=[
            SeaTalkWebhookAccount(
                account_id="default",
                app_id="app-default",
                signing_secret="default-signing",
                dispatch=default_dispatch or _noop_dispatch,
            ),
            SeaTalkWebhookAccount(
                account_id="staging",
                app_id="app-staging",
                signing_secret="staging-signing",
                dispatch=staging_dispatch or _noop_dispatch,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_t2_06_01_shared_server_merge():
    webhook_port = _free_port()
    default_dispatcher = FakeDispatcher()
    staging_dispatcher = FakeDispatcher()
    cfg = _config(
        accounts={
            "default": _webhook_account("app-default", webhook_port=webhook_port),
            "staging": _webhook_account("app-staging", webhook_port=webhook_port),
        },
        clients={"default": FakeClient(), "staging": FakeClient()},
        dispatchers={"default": default_dispatcher, "staging": staging_dispatcher},
    )
    seatalk = adapter.SeaTalkAdapter(cfg)

    assert await seatalk.connect() is True
    try:
        default_server = seatalk._runtimes["default"].webhook_server
        staging_server = seatalk._runtimes["staging"].webhook_server
        assert default_server is not None
        assert default_server is staging_server
        assert len(default_server.accounts) == 2
    finally:
        await seatalk.disconnect()


@pytest.mark.asyncio
async def test_t2_06_02_different_endpoint_separate_servers():
    default_port = _free_port()
    staging_port = _free_port()
    cfg = _config(
        accounts={
            "default": _webhook_account("app-default", webhook_port=default_port),
            "staging": _webhook_account("app-staging", webhook_port=staging_port),
        },
        clients={"default": FakeClient(), "staging": FakeClient()},
        dispatchers={"default": FakeDispatcher(), "staging": FakeDispatcher()},
    )
    seatalk = adapter.SeaTalkAdapter(cfg)

    assert await seatalk.connect() is True
    try:
        default_server = seatalk._runtimes["default"].webhook_server
        staging_server = seatalk._runtimes["staging"].webhook_server
        assert default_server is not None
        assert staging_server is not None
        assert default_server is not staging_server
    finally:
        await seatalk.disconnect()


@pytest.mark.asyncio
async def test_t2_06_03_signature_before_parse():
    server = _server()
    await server.start()
    try:
        body = b"{bad-json"
        async with aiohttp.ClientSession() as session:
            async with session.post(await _url(server), data=body, headers={"Signature": "bad"}) as resp:
                assert resp.status == 403
                assert await resp.text() == "Forbidden"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_t2_06_04_candidate_secret_routes_to_account():
    staging_received = []
    dispatched = asyncio.Event()

    async def staging_dispatch(event, source):
        staging_received.append((event, source))
        dispatched.set()

    server = _server(staging_dispatch=staging_dispatch)
    await server.start()
    try:
        body = json.dumps({
            "app_id": "app-staging",
            "event_type": "message_from_bot_subscriber",
            "event": {"x": 1},
        }).encode()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                await _url(server),
                data=body,
                headers={"Signature": _signature(body, "staging-signing")},
            ) as resp:
                assert resp.status == 200
        await asyncio.wait_for(dispatched.wait(), timeout=1)
        assert staging_received == [(json.loads(body.decode()), "webhook")]
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_t2_06_05_signature_no_match():
    server = _server()
    await server.start()
    try:
        body = json.dumps({"app_id": "app-default", "event_type": "message_from_bot_subscriber"}).encode()
        async with aiohttp.ClientSession() as session:
            async with session.post(await _url(server), data=body, headers={"Signature": "bad"}) as resp:
                assert resp.status == 403
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_t2_06_06_app_id_mismatch():
    server = _server()
    await server.start()
    try:
        body = json.dumps({"app_id": "app-staging", "event_type": "message_from_bot_subscriber"}).encode()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                await _url(server),
                data=body,
                headers={"Signature": _signature(body, "default-signing")},
            ) as resp:
                assert resp.status == 403
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_t2_06_07_challenge_without_app_id():
    server = _server()
    await server.start()
    try:
        body = json.dumps({
            "event_type": "event_verification",
            "event": {"seatalk_challenge": "challenge-1"},
        }).encode()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                await _url(server),
                data=body,
                headers={"Signature": _signature(body, "default-signing")},
            ) as resp:
                assert resp.status == 200
                assert await resp.json() == {"seatalk_challenge": "challenge-1"}
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_t2_06_08_normal_event_missing_app_id_rejected():
    server = _server()
    await server.start()
    try:
        body = json.dumps({"event_type": "message_from_bot_subscriber", "event": {}}).encode()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                await _url(server),
                data=body,
                headers={"Signature": _signature(body, "default-signing")},
            ) as resp:
                assert resp.status == 403
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_t2_06_09_unknown_app_id():
    server = _server()
    await server.start()
    try:
        body = json.dumps({"app_id": "app-unknown", "event_type": "message_from_bot_subscriber"}).encode()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                await _url(server),
                data=body,
                headers={"Signature": _signature(body, "default-signing")},
            ) as resp:
                assert resp.status == 403
                assert await resp.text() == "Forbidden"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_t2_06_10_dispatch_account_id():
    webhook_port = _free_port()
    dispatcher = FakeDispatcher()
    cfg = _config(
        accounts={
            "default": _webhook_account("app-default", webhook_port=webhook_port),
            "staging": _webhook_account("app-staging", webhook_port=webhook_port),
        },
        clients={"default": FakeClient(), "staging": FakeClient()},
        dispatchers={"default": FakeDispatcher(), "staging": dispatcher},
    )
    seatalk = adapter.SeaTalkAdapter(cfg)
    assert await seatalk.connect() is True
    try:
        server = seatalk._runtimes["staging"].webhook_server
        assert server is not None
        body = json.dumps({
            "app_id": "app-staging",
            "event_id": "event-1",
            "event_type": "message_from_bot_subscriber",
            "event": {"employee_code": "EmpABC", "message": {"message_id": "m1", "tag": "text", "text": {"plain_text": "hi"}}},
        }).encode()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                await _url(server),
                data=body,
                headers={"Signature": _signature(body, "app-staging-signing")},
            ) as resp:
                assert resp.status == 200
        for _ in range(20):
            if dispatcher.events:
                break
            await asyncio.sleep(0.01)
        assert dispatcher.events[0][0]["app_id"] == "app-staging"
    finally:
        await seatalk.disconnect()
