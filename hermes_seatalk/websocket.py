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
_DISPATCH_TIMEOUT_SECONDS = 30.0


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
            except Exception as exc:  # noqa: BLE001 - kick / socket / transient errors reconnect
                self.last_error = str(exc)
                logger.warning("SeaTalk websocket error: %s", exc)
            self.connected.clear()
            if self._stop.is_set() or self.auth_failed:
                break
            await self._sleep(backoff)
            backoff = min(backoff * 2, self.reconnect_max_seconds)

    async def _connect_once(self, sdk: Any) -> None:
        assert self._loop is not None
        dispatcher = sdk.EventDispatcher().on_event(self._on_event)
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
            await self._loop.run_in_executor(None, client.connect)
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

        Must not raise: an exception here would tear down the listen loop. We
        log and let the SDK ack so a single bad event doesn't drop the
        connection (matches webhook/relay, which also do not redeliver).
        """
        payload = getattr(event, "data", None)
        if not isinstance(payload, dict):
            return
        loop = self._loop
        if loop is None:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self.dispatch(payload, "websocket"), loop)
            future.result(timeout=_DISPATCH_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SeaTalk websocket dispatch failed: %s", exc)
