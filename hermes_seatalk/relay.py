"""SeaTalk relay WebSocket client."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp


logger = logging.getLogger(__name__)
DispatchFn = Callable[[dict[str, Any], str], Awaitable[None]]


class SeaTalkRelayClient:
    def __init__(
        self,
        *,
        relay_url: str,
        app_id: str,
        app_secret: str,
        signing_secret: str,
        dispatch: DispatchFn,
        reconnect_initial_seconds: float = 1.0,
        reconnect_max_seconds: float = 30.0,
        heartbeat_timeout_seconds: float = 60.0,
        sleep_fn=asyncio.sleep,
    ):
        self.relay_url = relay_url
        self.app_id = app_id
        self.app_secret = app_secret
        self.signing_secret = signing_secret
        self.dispatch = dispatch
        self.reconnect_initial_seconds = reconnect_initial_seconds
        self.reconnect_max_seconds = reconnect_max_seconds
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self._sleep = sleep_fn
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.connected = asyncio.Event()
        self.auth_failed = False
        self.last_error: str | None = None

    async def start(self, *, wait_authenticated: bool = True, timeout: float = 5.0) -> bool:
        self._stop.clear()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        if not wait_authenticated:
            return True
        try:
            await asyncio.wait_for(self.connected.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def stop(self) -> None:
        self._stop.set()
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        if self._session is not None:
            await self._session.close()
        self._session = None
        self.connected.clear()

    async def _run(self) -> None:
        backoff = self.reconnect_initial_seconds
        self._session = aiohttp.ClientSession()
        while not self._stop.is_set() and not self.auth_failed:
            try:
                await self._connect_once()
                backoff = self.reconnect_initial_seconds
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                logger.warning("SeaTalk relay error: %s", exc)
                if self.auth_failed:
                    break
            self.connected.clear()
            if self._stop.is_set() or self.auth_failed:
                break
            await self._sleep(backoff)
            backoff = min(backoff * 2, self.reconnect_max_seconds)

    async def _connect_once(self) -> None:
        assert self._session is not None
        async with self._session.ws_connect(self.relay_url) as ws:
            self._ws = ws
            await ws.send_json({
                "type": "auth",
                "appId": self.app_id,
                "appSecret": self.app_secret,
                "signingSecret": self.signing_secret,
            })
            authenticated = False

            while not self._stop.is_set():
                try:
                    msg = await ws.receive(timeout=self.heartbeat_timeout_seconds)
                except asyncio.TimeoutError:
                    self.last_error = "heartbeat timeout"
                    return

                if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    return
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue

                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    logger.warning("SeaTalk relay sent malformed JSON")
                    continue
                if not isinstance(data, dict):
                    continue

                msg_type = data.get("type")
                if not authenticated:
                    if msg_type == "auth_ok":
                        authenticated = True
                        self.last_error = None
                        self.connected.set()
                    elif msg_type == "auth_fail":
                        self.auth_failed = True
                        self.last_error = str(data.get("error") or "relay auth failed")
                        return
                    continue

                if msg_type == "event" and isinstance(data.get("event"), dict):
                    await self.dispatch(data["event"], "relay")
                elif msg_type == "ping":
                    await ws.send_json({"type": "pong"})
                elif msg_type == "replaced":
                    self.auth_failed = True
                    self.last_error = "connection replaced by another instance"
                    return
                else:
                    logger.info("SeaTalk relay unknown message type: %s", msg_type)

