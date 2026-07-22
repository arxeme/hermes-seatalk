from __future__ import annotations

import asyncio

import pytest

from hermes_seatalk.adapter import (
    DEFAULT_WEBSOCKET_URL,
    VALID_MODES,
    _accounts_from_extra,
    _build_account_config,
)
from hermes_seatalk.websocket import SeaTalkWebSocketClient, _import_sdk


sdk = _import_sdk()


async def _noop_sleep(_delay):
    await asyncio.sleep(0)


class _FakeSDKClient:
    """Stands in for seatalk_oapi_sdk.Client.

    Delivers a list of event payloads through the *real* SDK EventDispatcher
    (exercising SeaTalkWebSocketClient._on_event and the SDK's auto-ack), then
    blocks in start() until the stop event fires, like the real listen loop.
    """

    def __init__(self, dispatcher, events, *, register_error=None):
        self.dispatcher = dispatcher
        self.events = events
        self.register_error = register_error
        self.acked: list[str] = []
        self.closed = False
        self.started = asyncio.get_event_loop()

    def connect(self):
        if self.register_error is not None:
            raise self.register_error
        return sdk.RegisterResult(app_id="app-id", token="tok", heartbeat_interval=15.0)

    def ack(self, callback_id):
        self.acked.append(callback_id)

    def start(self, stop_event):
        for index, data in enumerate(self.events):
            env = sdk.Envelope(
                cmd=sdk.COMMAND_EVENT,
                header=sdk.Header(app_id="app-id", callback_id=f"cb{index}"),
                data=data,
            )
            self.dispatcher.dispatch(self, env)
        stop_event.wait()

    def close(self):
        self.closed = True


def _ws_client(dispatch, events, *, register_error=None, ws_url="wss://example/ws", **kwargs):
    holder: dict = {}

    def factory(app_id, app_secret, url, dispatcher):
        client = _FakeSDKClient(dispatcher, events, register_error=register_error)
        holder["client"] = client
        holder["ws_url"] = url
        return client

    ws = SeaTalkWebSocketClient(
        ws_url=ws_url,
        app_id="app-id",
        app_secret="app-secret",
        dispatch=dispatch,
        reconnect_initial_seconds=kwargs.pop("reconnect_initial_seconds", 0),
        reconnect_max_seconds=kwargs.pop("reconnect_max_seconds", 0),
        sleep_fn=kwargs.pop("sleep_fn", _noop_sleep),
        client_factory=factory,
        **kwargs,
    )
    return ws, holder


@pytest.mark.asyncio
async def test_t13_01_websocket_connect_and_dispatch():
    received: list = []
    dispatched = asyncio.Event()

    async def dispatch(event, source):
        received.append((event, source))
        dispatched.set()

    payload = {
        "event_id": "e1",
        "event_type": "message_from_bot_subscriber",
        "app_id": "app-id",
        "event": {"employee_code": "EmpABC", "message": {"tag": "text"}},
    }
    ws, holder = _ws_client(dispatch, [payload])
    try:
        assert await ws.start(timeout=1) is True
        assert ws.connected.is_set() is True
        await asyncio.wait_for(dispatched.wait(), timeout=1)
        assert received == [(payload, "websocket")]
        # Registering the generic on_event handler must trigger the SDK auto-ack.
        # The ack runs on the SDK thread just after dispatch, so poll briefly.
        for _ in range(100):
            if holder["client"].acked == ["cb0"]:
                break
            await asyncio.sleep(0.01)
        assert holder["client"].acked == ["cb0"]
    finally:
        await ws.stop()


@pytest.mark.asyncio
async def test_t13_02_register_error_marks_auth_failed():
    ws, _ = _ws_client(
        lambda _e, _s: None,
        [],
        register_error=sdk.RegisterError(1, "bad credentials"),
        reconnect_initial_seconds=60,
        reconnect_max_seconds=60,
        sleep_fn=asyncio.sleep,
    )
    try:
        assert await ws.start(timeout=1) is False
        assert ws.auth_failed is True
        assert ws.connected.is_set() is False
        assert "register failed" in (ws.last_error or "")
    finally:
        await ws.stop()


@pytest.mark.asyncio
async def test_t13_03_stop_exits_cleanly():
    ws, holder = _ws_client(lambda _e, _s: None, [])
    try:
        assert await ws.start(timeout=1) is True
        await ws.stop()
        assert ws._task is None
        assert ws.connected.is_set() is False
        assert holder["client"].closed is True
    finally:
        await ws.stop()


def test_t13_04_default_ws_url_when_blank():
    ws = SeaTalkWebSocketClient(
        ws_url="",
        app_id="a",
        app_secret="s",
        dispatch=lambda _e, _s: None,
    )
    assert ws.ws_url == DEFAULT_WEBSOCKET_URL


def test_t13_05_websocket_mode_config_defaults():
    assert "websocket" in VALID_MODES
    config = _build_account_config(
        "default",
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "signing_secret": "signing",
            "mode": "websocket",
        },
    )
    assert config.mode == "websocket"
    assert config.ws_url == DEFAULT_WEBSOCKET_URL
    # Default outbound format is Markdown (2) per product decision.
    assert config.text_format == 2


def test_t13_06_websocket_custom_ws_url_and_text_format():
    config = _build_account_config(
        "default",
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "signing_secret": "signing",
            "mode": "websocket",
            "ws_url": "wss://custom.example/ws/bot",
            "text_format": 1,
        },
    )
    assert config.ws_url == "wss://custom.example/ws/bot"
    assert config.text_format == 1


def test_t13_07_invalid_text_format_rejected():
    with pytest.raises(ValueError, match="text_format"):
        _build_account_config(
            "default",
            {
                "app_id": "app-id",
                "app_secret": "secret",
                "signing_secret": "signing",
                "mode": "websocket",
                "text_format": 3,
            },
        )


def test_t13_09_ws_lifecycle_events_are_log_only():
    from hermes_seatalk.dispatcher import LOG_ONLY_EVENTS, SUPPORTED_MESSAGE_EVENTS

    # Native-WS lifecycle events must be classified log-only (not "unknown").
    assert "user_enter_chatroom_with_bot" in LOG_ONLY_EVENTS
    assert "group_chat_converted_to_external_group" in LOG_ONLY_EVENTS
    # And must not be treated as message events.
    assert "user_enter_chatroom_with_bot" not in SUPPORTED_MESSAGE_EVENTS


def test_t13_08_websocket_account_via_extra():
    accounts = _accounts_from_extra(
        {
            "accounts": {
                "default": {
                    "app_id": "app-id",
                    "app_secret": "secret",
                    "signing_secret": "signing",
                    "mode": "websocket",
                }
            }
        }
    )
    assert accounts["default"].mode == "websocket"
    assert accounts["default"].ws_url == DEFAULT_WEBSOCKET_URL


def test_t13_10_signing_secret_optional_for_websocket_required_otherwise():
    # websocket: signing_secret not required (SDK authenticates with app creds).
    cfg = _build_account_config(
        "default", {"app_id": "a", "app_secret": "b", "mode": "websocket"}
    )
    assert cfg.mode == "websocket"
    assert cfg.signing_secret == ""
    # relay/webhook still require signing_secret.
    with pytest.raises(ValueError, match="signing_secret"):
        _build_account_config(
            "default",
            {"app_id": "a", "app_secret": "b", "mode": "relay", "relay_url": "wss://x/ws"},
        )
    with pytest.raises(ValueError, match="signing_secret"):
        _build_account_config("default", {"app_id": "a", "app_secret": "b", "mode": "webhook"})


@pytest.mark.asyncio
async def test_t13_11_kick_backs_off_to_max_and_is_not_auth_failure():
    delays: list[float] = []

    async def recording_sleep(delay):
        delays.append(delay)
        await asyncio.sleep(0)

    calls = {"n": 0}
    reconnected = asyncio.Event()

    class _KickThenIdleClient:
        def __init__(self, dispatcher):
            self.dispatcher = dispatcher

        def connect(self):
            return sdk.RegisterResult(app_id="app-id", token="tok")

        def ack(self, callback_id):
            pass

        def start(self, stop_event):
            calls["n"] += 1
            if calls["n"] == 1:
                raise sdk.KickError("replaced by another connection")
            reconnected.set()
            stop_event.wait()

        def close(self):
            pass

    ws = SeaTalkWebSocketClient(
        ws_url="wss://example/ws",
        app_id="app-id",
        app_secret="app-secret",
        dispatch=lambda _e, _s: None,
        reconnect_initial_seconds=1,
        reconnect_max_seconds=30,
        sleep_fn=recording_sleep,
        client_factory=lambda a, s, u, d: _KickThenIdleClient(d),
    )
    try:
        assert await ws.start(timeout=1) is True
        await asyncio.wait_for(reconnected.wait(), timeout=1)
        # Kick must not be treated as an auth failure, and backoff jumps to max
        # (not the 1s initial value that would cause a tight mutual-kick loop).
        assert ws.auth_failed is False
        assert 30 in delays
        assert 1 not in delays
    finally:
        await ws.stop()
