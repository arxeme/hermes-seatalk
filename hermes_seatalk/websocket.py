"""SeaTalk native WebSocket Event Callback client.

This wraps the official ``seatalk_oapi_sdk`` (pure-stdlib, no third-party deps)
so the bot receives real-time events over an outbound WebSocket connection —
no public inbound HTTP endpoint and no self-hosted relay required.

The SDK is blocking/thread-based, so the connection runs on the default
executor and incoming events are bridged back onto the gateway event loop with
``run_coroutine_threadsafe``. The class deliberately mirrors the
``SeaTalkRelayClient`` interface (``start``/``stop``/``connected``/
``auth_failed``/``last_error``/``_task``) so the adapter's runtime monitor and
disconnect paths can treat both inbound transports uniformly.
"""

from __future__ import annotations

import asyncio
import logging
import socket as _socket
import sys
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)
DispatchFn = Callable[[dict[str, Any], str], Awaitable[None]]

# Matches seatalk_oapi_sdk.DEFAULT_WEB_SOCKET_URL; kept here so the adapter can
# default config without importing the SDK at module load time.
DEFAULT_WEBSOCKET_URL = "wss://ws-openapi.haiserve.com/ws/bot"
_TCP_KEEPALIVE_IDLE_SECONDS = 60


def _import_sdk() -> Any:
    """Import the SeaTalk OAPI SDK, falling back to the bundled copy under ref/.

    The SDK is pure-stdlib, so the bundled-path fallback is sufficient when the
    package is not pip-installed in the Hermes virtualenv.
    """
    try:
        import seatalk_oapi_sdk  # type: ignore[import-not-found]

        return seatalk_oapi_sdk
    except ImportError:
        bundled = (
            Path(__file__).resolve().parent.parent
            / "ref"
            / "seatalk-oapi"
            / "seatalk-oapi-sdk-py"
        )
        if bundled.is_dir() and str(bundled) not in sys.path:
            sys.path.insert(0, str(bundled))
        import seatalk_oapi_sdk  # type: ignore[import-not-found]

        return seatalk_oapi_sdk


class SeaTalkWebSocketClient:
    def __init__(
        self,
        *,
        ws_url: str,
        app_id: str,
        app_secret: str,
        dispatch: DispatchFn,
        reconnect_initial_seconds: float = 1.0,
        reconnect_max_seconds: float = 30.0,
        sleep_fn=asyncio.sleep,
        client_factory: Any = None,
    ):
        self.ws_url = ws_url or DEFAULT_WEBSOCKET_URL
        self.app_id = app_id
        self.app_secret = app_secret
        self.dispatch = dispatch
        self.reconnect_initial_seconds = reconnect_initial_seconds
        self.reconnect_max_seconds = reconnect_max_seconds
        self._sleep = sleep_fn
        self._client_factory = client_factory
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._client: Any = None
        self._stop = asyncio.Event()
        self._thread_stop = threading.Event()
        self.connected = asyncio.Event()
        self.auth_failed = False
        self.last_error: str | None = None

    async def start(self, *, wait_authenticated: bool = True, timeout: float = 5.0) -> bool:
        self._loop = asyncio.get_running_loop()
        self._stop.clear()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        if not wait_authenticated:
            return True
        deadline = self._loop.time() + timeout
        while not self.connected.is_set() and not self.auth_failed:
            remaining = deadline - self._loop.time()
            if remaining <= 0:
                return False
            try:
                await asyncio.wait_for(self.connected.wait(), timeout=min(remaining, 0.05))
            except asyncio.TimeoutError:
                continue
        return self.connected.is_set()

    async def stop(self) -> None:
        self._stop.set()
        self._thread_stop.set()
        client = self._client
        if client is not None:
            try:
                await asyncio.get_running_loop().run_in_executor(None, client.close)
            except Exception:  # noqa: BLE001
                pass
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        self.connected.clear()

    async def _run(self) -> None:
        sdk = _import_sdk()
        backoff = self.reconnect_initial_seconds
        while not self._stop.is_set() and not self.auth_failed:
            try:
                await self._connect_once(sdk)
                backoff = self.reconnect_initial_seconds
            except asyncio.CancelledError:
                raise
            except sdk.RegisterError as exc:
                self.auth_failed = True
                self.last_error = f"register failed: code={getattr(exc, 'code', '?')} {exc}"
                logger.warning("SeaTalk websocket auth failed: %s", self.last_error)
            except sdk.MissingCredentialError as exc:
                self.auth_failed = True
                self.last_error = str(exc)
                logger.warning("SeaTalk websocket missing credentials: %s", exc)
            except sdk.KickError as exc:
                # Another connection for this app replaced us. Back off fully
                # before reconnecting; otherwise two instances kick each other
                # in a tight loop.
                self.last_error = f"kicked by another connection: {exc}"
                logger.warning("SeaTalk websocket %s; backing off to max before reconnect", self.last_error)
                backoff = self.reconnect_max_seconds
            except Exception as exc:  # noqa: BLE001 - socket / transient errors reconnect
                self.last_error = str(exc)
                logger.warning("SeaTalk websocket error: %s", exc)
            self.connected.clear()
            if self._stop.is_set() or self.auth_failed:
                break
            await self._sleep(backoff)
            backoff = min(backoff * 2, self.reconnect_max_seconds)

    async def _connect_once(self, sdk: Any) -> None:
        assert self._loop is not None
        # on_event drives dispatch + auto-ack. Suppress the SDK's default
        # on_envelope handler (it prints every event payload to stdout) and route
        # malformed frames to our logger instead.
        dispatcher = (
            sdk.EventDispatcher()
            .on_event(self._on_event)
            .on_envelope(None)
            .on_invalid_frame(
                lambda payload, err: logger.warning("SeaTalk websocket invalid frame: %s", err)
            )
        )
        if self._client_factory is not None:
            client = self._client_factory(self.app_id, self.app_secret, self.ws_url, dispatcher)
        else:
            client = sdk.Client(
                app_id=self.app_id,
                app_secret=self.app_secret,
                ws_url=self.ws_url,
                dispatcher=dispatcher,
                logger=logger,
            )
        self._client = client
        self._thread_stop.clear()
        try:
            # connect(): WebSocket handshake + register; raises RegisterError on
            # bad credentials. start(stop_event): blocks reading events (and runs
            # the SDK's internal heartbeat) until the stop event is set or the
            # connection drops.
            register_result = await self._loop.run_in_executor(None, client.connect)
            _tune_ping_interval(client, register_result)
            _apply_tcp_keepalive(client)
            self.last_error = None
            self.connected.set()
            await self._loop.run_in_executor(None, lambda: client.start(self._thread_stop))
        finally:
            self.connected.clear()
            try:
                await self._loop.run_in_executor(None, client.close)
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    def _on_event(self, event: Any) -> None:
        """SDK ``on_event`` callback. Runs in the SDK listen thread.

        Registering this generic handler is what makes the SDK auto-``ack`` each
        event after we return (developer guide §10). The SDK ``Event.data`` is
        the raw ``{event_id, event_type, app_id, event: {...}}`` payload, which
        is exactly the shape ``SeaTalkEventDispatcher`` already consumes for
        webhook/relay — so no inbound parsing changes are needed.

        Acks on receipt: we schedule dispatch on the gateway loop and return
        immediately so the SDK acks now, without waiting for normalization,
        inbound media download, or agent processing (which could exceed the
        server's ack timeout and trigger redelivery). ``event_id`` dedup in the
        dispatcher guards against any redelivery. Returning without raising also
        keeps a single bad event from tearing down the listen loop.
        """
        payload = getattr(event, "data", None)
        if not isinstance(payload, dict):
            return
        loop = self._loop
        if loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._safe_dispatch(payload), loop)

    async def _safe_dispatch(self, payload: dict[str, Any]) -> None:
        try:
            await self.dispatch(payload, "websocket")
        except Exception as exc:  # noqa: BLE001
            logger.warning("SeaTalk websocket dispatch failed: %s", exc)


def _tune_ping_interval(client: Any, register_result: Any) -> None:
    """Keep the session alive when the server's heartbeat_timeout is shorter
    than its heartbeat_interval.

    The SDK pings every ``heartbeat_interval`` and ignores ``heartbeat_timeout``.
    The server has been observed returning interval=20/timeout=10: it marks the
    session dead 10s after register — before the first ping — and silently stops
    delivering events while keeping the TCP connection open. Ping at
    ``min(interval, timeout / 2)`` so the session stays alive under either
    parameter regime (verified live: 5s pings restore delivery and Re-verify).
    """
    try:
        interval = float(getattr(register_result, "heartbeat_interval", 0) or 0)
        timeout = float(getattr(register_result, "heartbeat_timeout", 0) or 0)
        if timeout <= 0:
            return
        current = float(getattr(client, "ping_interval", 0) or interval or 15.0)
        tuned = max(1.0, min(current, timeout / 2))
        if tuned != current:
            client.ping_interval = tuned
            logger.info(
                "SeaTalk websocket ping interval tuned: interval=%s timeout=%s -> ping every %ss",
                interval,
                timeout,
                tuned,
            )
    except Exception:  # noqa: BLE001
        pass


def _apply_tcp_keepalive(client: Any, idle_seconds: int = _TCP_KEEPALIVE_IDLE_SECONDS) -> None:
    """Best-effort SO_KEEPALIVE on the SDK's underlying socket.

    The SDK reads without a socket timeout and relies on heartbeat-send failure
    to notice a dead peer; TCP keepalive lets the OS detect a silently-dropped
    connection so reconnect happens sooner. Best-effort: the socket lives on a
    private SDK attribute, so silently skip if unavailable.
    """
    try:
        sock = client._conn._sock  # type: ignore[attr-defined]
        if sock is None:
            return
        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_KEEPALIVE, 1)
        if hasattr(_socket, "TCP_KEEPIDLE"):
            sock.setsockopt(_socket.IPPROTO_TCP, _socket.TCP_KEEPIDLE, idle_seconds)
    except Exception:  # noqa: BLE001
        pass
