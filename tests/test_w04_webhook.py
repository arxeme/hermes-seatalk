from __future__ import annotations

import asyncio
import hashlib
import json
import socket
from types import SimpleNamespace

import aiohttp
import pytest

from hermes_seatalk import adapter
from hermes_seatalk.webhook import SeaTalkWebhookServer


def _signature(body: bytes, secret: str = "signing-secret") -> str:
    return hashlib.sha256(body + secret.encode("latin1")).hexdigest()


async def _url(server: SeaTalkWebhookServer) -> str:
    sockets = server.site._server.sockets  # type: ignore[union-attr, attr-defined]
    host, port = sockets[0].getsockname()[:2]
    return f"http://{host}:{port}{server.path}"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
async def test_t04_01_valid_event_enters_dispatch():
    received = []

    async def dispatch(event, source):
        received.append((event, source))

    server = SeaTalkWebhookServer(
        host="127.0.0.1",
        port=0,
        path="/callback",
        signing_secret="signing-secret",
        dispatch=dispatch,
    )
    await server.start()
    try:
        body = json.dumps({"event_type": "message_from_bot_subscriber", "event": {"x": 1}}).encode()
        async with aiohttp.ClientSession() as session:
            async with session.post(await _url(server), data=body, headers={"Signature": _signature(body)}) as resp:
                assert resp.status == 200
                assert await resp.text() == "OK"
        for _ in range(20):
            if received:
                break
            await asyncio.sleep(0.01)
        assert received == [({"event_type": "message_from_bot_subscriber", "event": {"x": 1}}, "webhook")]
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_t04_02_invalid_signature_rejected():
    called = False

    async def dispatch(_event, _source):
        nonlocal called
        called = True

    server = SeaTalkWebhookServer(
        host="127.0.0.1",
        port=0,
        path="/callback",
        signing_secret="signing-secret",
        dispatch=dispatch,
    )
    await server.start()
    try:
        body = b'{"event_type":"message_from_bot_subscriber"}'
        async with aiohttp.ClientSession() as session:
            async with session.post(await _url(server), data=body, headers={"Signature": "bad"}) as resp:
                assert resp.status == 403
        assert called is False
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_t04_03_event_verification_returns_challenge():
    async def dispatch(_event, _source):
        raise AssertionError("event_verification must not dispatch")

    server = SeaTalkWebhookServer(
        host="127.0.0.1",
        port=0,
        path="/callback",
        signing_secret="signing-secret",
        dispatch=dispatch,
    )
    await server.start()
    try:
        body = json.dumps({
            "event_type": "event_verification",
            "event": {"seatalk_challenge": "challenge-1"},
        }).encode()
        async with aiohttp.ClientSession() as session:
            async with session.post(await _url(server), data=body, headers={"Signature": _signature(body)}) as resp:
                assert resp.status == 200
                assert await resp.json() == {"seatalk_challenge": "challenge-1"}
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_t04_04_malformed_payload_rejected():
    async def dispatch(_event, _source):
        raise AssertionError("malformed payload must not dispatch")

    server = SeaTalkWebhookServer(
        host="127.0.0.1",
        port=0,
        path="/callback",
        signing_secret="signing-secret",
        dispatch=dispatch,
    )
    await server.start()
    try:
        body = b"{bad-json"
        async with aiohttp.ClientSession() as session:
            async with session.post(await _url(server), data=body, headers={"Signature": _signature(body)}) as resp:
                assert resp.status == 400
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_t04_05_fast_ack_does_not_wait_for_dispatch():
    started = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(_event, _source):
        started.set()
        await release.wait()

    server = SeaTalkWebhookServer(
        host="127.0.0.1",
        port=0,
        path="/callback",
        signing_secret="signing-secret",
        dispatch=dispatch,
    )
    await server.start()
    try:
        body = json.dumps({"event_type": "message_from_bot_subscriber", "event": {}}).encode()
        async with aiohttp.ClientSession() as session:
            async with session.post(await _url(server), data=body, headers={"Signature": _signature(body)}) as resp:
                assert resp.status == 200
        await asyncio.wait_for(started.wait(), timeout=1)
        release.set()
    finally:
        await server.stop()


@pytest.mark.asyncio
@pytest.mark.requires_hermes
async def test_t04_06_adapter_webhook_updates_health(monkeypatch):
    monkeypatch.delenv("SEATALK_WEBHOOK_PORT", raising=False)
    client = SimpleNamespace(close=lambda: None)
    cfg = SimpleNamespace(extra={
        "app_id": "app-id",
        "app_secret": "app-secret",
        "signing_secret": "signing-secret",
        "mode": "webhook",
        "webhook_host": "127.0.0.1",
        "webhook_port": str(_free_port()),
        "client": client,
    })
    seatalk = adapter.SeaTalkAdapter(cfg)
    assert await seatalk.connect() is True
    try:
        await seatalk._dispatch_event({"event_type": "message_from_bot_subscriber"}, "webhook")
        assert seatalk.is_connected is True
    finally:
        await seatalk.disconnect()


@pytest.mark.asyncio
async def test_t04_07_event_verification_invalid_signature_rejected():
    async def dispatch(_event, _source):
        raise AssertionError("invalid verification must not dispatch")

    server = SeaTalkWebhookServer(
        host="127.0.0.1",
        port=0,
        path="/callback",
        signing_secret="signing-secret",
        dispatch=dispatch,
    )
    await server.start()
    try:
        body = json.dumps({
            "event_type": "event_verification",
            "event": {"seatalk_challenge": "challenge-1"},
        }).encode()
        async with aiohttp.ClientSession() as session:
            async with session.post(await _url(server), data=body, headers={"Signature": "bad"}) as resp:
                assert resp.status == 403
                assert "seatalk_challenge" not in await resp.text()
    finally:
        await server.stop()
