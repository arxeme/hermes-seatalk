"""SeaTalk direct webhook server."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web


MAX_BODY_BYTES = 1024 * 1024
logger = logging.getLogger(__name__)
DispatchFn = Callable[[dict[str, Any], str], Awaitable[None]]


def verify_signature(raw_body: bytes, signing_secret: str, signature: str | None) -> bool:
    if not signature:
        return False
    calculated = hashlib.sha256(raw_body + signing_secret.encode("utf-8")).hexdigest()
    return hmac.compare_digest(calculated, signature)


class SeaTalkWebhookServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        path: str,
        signing_secret: str,
        dispatch: DispatchFn,
    ):
        self.host = host
        self.port = port
        self.path = path if path.startswith("/") else f"/{path}"
        self.signing_secret = signing_secret
        self.dispatch = dispatch
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        app = web.Application(client_max_size=MAX_BODY_BYTES)
        app.router.add_post(self.path, self.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

    async def stop(self) -> None:
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        if self.runner is not None:
            await self.runner.cleanup()
        self.runner = None
        self.site = None

    async def handle(self, request: web.Request) -> web.Response:
        try:
            raw_body = await request.read()
        except Exception:  # noqa: BLE001
            return web.Response(status=413, text="Payload Too Large")

        signature = request.headers.get("Signature")
        if not verify_signature(raw_body, self.signing_secret, signature):
            return web.Response(status=403, text="Forbidden")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return web.Response(status=400, text="Malformed JSON")
        if not isinstance(payload, dict):
            return web.Response(status=400, text="Malformed payload")

        if payload.get("event_type") == "event_verification":
            challenge = {}
            event = payload.get("event")
            if isinstance(event, dict):
                challenge = {"seatalk_challenge": event.get("seatalk_challenge")}
            return web.json_response(challenge)

        task = asyncio.create_task(self.dispatch(payload, "webhook"))
        self.tasks.add(task)
        task.add_done_callback(self._task_done)
        return web.Response(status=200, text="OK")

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self.tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.warning("SeaTalk webhook dispatch failed: %s", exc)

