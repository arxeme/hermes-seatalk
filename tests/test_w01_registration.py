from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import adapter


SEATALK_ENV = [
    "SEATALK_APP_ID",
    "SEATALK_APP_SECRET",
    "SEATALK_SIGNING_SECRET",
    "SEATALK_MODE",
    "SEATALK_RELAY_URL",
    "SEATALK_WEBHOOK_PORT",
]


class FakeContext:
    def __init__(self):
        self.platforms = []

    def register_platform(self, **kwargs):
        self.platforms.append(kwargs)


def _clear_env(monkeypatch):
    for name in SEATALK_ENV:
        monkeypatch.delenv(name, raising=False)


def _set_base_env(monkeypatch, mode="relay"):
    monkeypatch.setitem(sys.modules, "aiohttp", ModuleType("aiohttp"))
    monkeypatch.setenv("SEATALK_APP_ID", "app-id")
    monkeypatch.setenv("SEATALK_APP_SECRET", "app-secret")
    monkeypatch.setenv("SEATALK_SIGNING_SECRET", "signing-secret")
    monkeypatch.setenv("SEATALK_MODE", mode)


def _config(**extra):
    return SimpleNamespace(extra=extra)


def test_t01_01_minimal_relay_config_registers_platform(monkeypatch):
    _clear_env(monkeypatch)
    _set_base_env(monkeypatch, mode="relay")
    monkeypatch.setenv("SEATALK_RELAY_URL", "wss://relay.example/ws")

    ctx = FakeContext()
    adapter.register(ctx)

    assert len(ctx.platforms) == 1
    entry = ctx.platforms[0]
    assert entry["name"] == "seatalk"
    assert entry["label"] == "SeaTalk"
    assert entry["check_fn"] is adapter.check_seatalk_requirements
    assert entry["validate_config"] is adapter._validate_seatalk_config
    assert entry["is_connected"] is adapter._is_seatalk_connected
    assert entry["required_env"] == adapter.REQUIRED_ENV
    assert entry["allowed_users_env"] == "SEATALK_ALLOWED_USERS"
    assert entry["allow_all_env"] == "SEATALK_ALLOW_ALL_USERS"
    assert entry["max_message_length"] == 4000


def test_t01_02_missing_credentials_fail(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SEATALK_APP_ID", "app-id")
    monkeypatch.setenv("SEATALK_APP_SECRET", "app-secret")
    monkeypatch.setenv("SEATALK_MODE", "webhook")

    assert adapter.check_seatalk_requirements() is False
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        app_secret="app-secret",
        mode="webhook",
    )) is False


def test_t01_03_relay_url_required_only_for_relay(monkeypatch):
    _clear_env(monkeypatch)
    _set_base_env(monkeypatch, mode="relay")

    assert adapter.check_seatalk_requirements() is False
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        app_secret="app-secret",
        signing_secret="signing-secret",
        mode="relay",
    )) is False

    monkeypatch.setenv("SEATALK_RELAY_URL", "wss://relay.example/ws")
    assert adapter.check_seatalk_requirements() is True
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        app_secret="app-secret",
        signing_secret="signing-secret",
        mode="relay",
        relay_url="wss://relay.example/ws",
    )) is True


def test_t01_04_webhook_does_not_require_relay_url(monkeypatch):
    _clear_env(monkeypatch)
    _set_base_env(monkeypatch, mode="webhook")

    assert adapter.check_seatalk_requirements() is True
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        app_secret="app-secret",
        signing_secret="signing-secret",
        mode="webhook",
    )) is True


def test_t01_05_is_connected_matches_validate_config(monkeypatch):
    _clear_env(monkeypatch)
    cfg = _config(
        app_id="app-id",
        app_secret="app-secret",
        signing_secret="signing-secret",
        mode="webhook",
    )

    assert adapter._is_seatalk_connected(cfg) is adapter._validate_seatalk_config(cfg)


def test_t01_06_runtime_health_does_not_affect_connected(monkeypatch):
    _clear_env(monkeypatch)
    cfg = _config(
        app_id="app-id",
        app_secret="app-secret",
        signing_secret="signing-secret",
        mode="webhook",
    )

    assert adapter._is_seatalk_connected(cfg) is True


def test_t01_07_invalid_mode_is_rejected(monkeypatch):
    _clear_env(monkeypatch)
    _set_base_env(monkeypatch, mode="socket")

    assert adapter.check_seatalk_requirements() is False
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        app_secret="app-secret",
        signing_secret="signing-secret",
        mode="socket",
    )) is False


def test_t01_08_register_is_repeatable(monkeypatch):
    _clear_env(monkeypatch)
    ctx = FakeContext()

    adapter.register(ctx)
    adapter.register(ctx)

    assert [entry["name"] for entry in ctx.platforms] == ["seatalk"]
