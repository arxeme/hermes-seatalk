from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from hermes_seatalk import adapter


SEATALK_ENV = [
    "SEATALK_APP_SECRET",
    "SEATALK_SIGNING_SECRET",
    "HERMES_SEATALK_ALLOWED_USERS",
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
    del mode
    monkeypatch.setitem(sys.modules, "aiohttp", ModuleType("aiohttp"))
    monkeypatch.setenv("SEATALK_APP_SECRET", "app-secret")
    monkeypatch.setenv("SEATALK_SIGNING_SECRET", "signing-secret")


def _set_config_file_extra(monkeypatch, **extra):
    monkeypatch.setattr(adapter, "_config_file_extra", lambda: extra)


def _config(**extra):
    return SimpleNamespace(extra=extra)


def test_t01_01_minimal_relay_config_registers_platform(monkeypatch):
    _clear_env(monkeypatch)
    _set_base_env(monkeypatch, mode="relay")
    _set_config_file_extra(
        monkeypatch,
        app_id="app-id",
        mode="relay",
        relay_url="wss://relay.example/ws",
        allow_from=["alice@example.com"],
    )

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
    assert entry["allowed_users_env"] == "HERMES_SEATALK_ALLOWED_USERS"
    assert "allow_all_env" not in entry
    assert entry["max_message_length"] == 4000
    assert adapter.os.environ["HERMES_SEATALK_ALLOWED_USERS"] == "alice@example.com"


def test_t01_02_missing_credentials_fail(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SEATALK_APP_SECRET", "app-secret")
    _set_config_file_extra(monkeypatch, app_id="app-id", mode="webhook")

    assert adapter.check_seatalk_requirements() is False
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        app_secret="app-secret",
        mode="webhook",
    )) is False


def test_t01_03_relay_url_required_only_for_relay(monkeypatch):
    _clear_env(monkeypatch)
    _set_base_env(monkeypatch, mode="relay")
    _set_config_file_extra(monkeypatch, app_id="app-id", mode="relay")

    assert adapter.check_seatalk_requirements() is False
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        app_secret="app-secret",
        signing_secret="signing-secret",
        mode="relay",
    )) is False

    _set_config_file_extra(
        monkeypatch,
        app_id="app-id",
        mode="relay",
        relay_url="wss://relay.example/ws",
    )
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
    _set_config_file_extra(monkeypatch, app_id="app-id", mode="webhook")

    assert adapter.check_seatalk_requirements() is True
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        app_secret="app-secret",
        signing_secret="signing-secret",
        mode="webhook",
    )) is True


def test_t01_05_is_connected_matches_validate_config(monkeypatch):
    _clear_env(monkeypatch)
    _set_base_env(monkeypatch)
    cfg = _config(
        app_id="app-id",
        mode="webhook",
    )

    assert adapter._is_seatalk_connected(cfg) is adapter._validate_seatalk_config(cfg)


def test_t01_06_runtime_health_does_not_affect_connected(monkeypatch):
    _clear_env(monkeypatch)
    _set_base_env(monkeypatch)
    cfg = _config(
        app_id="app-id",
        mode="webhook",
    )

    assert adapter._is_seatalk_connected(cfg) is True


def test_t01_07_invalid_mode_is_rejected(monkeypatch):
    _clear_env(monkeypatch)
    _set_base_env(monkeypatch, mode="socket")
    _set_config_file_extra(monkeypatch, app_id="app-id", mode="socket")

    assert adapter.check_seatalk_requirements() is False
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        app_secret="app-secret",
        signing_secret="signing-secret",
        mode="socket",
    )) is False


def test_t01_08_invalid_policy_is_rejected(monkeypatch):
    _clear_env(monkeypatch)
    _set_base_env(monkeypatch)

    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        mode="webhook",
        dm_policy="everyone",
    )) is False
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        mode="webhook",
        group_policy="everyone",
    )) is False
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        mode="webhook",
        processing_indicator="spinner",
    )) is False
    assert adapter._validate_seatalk_config(_config(
        app_id="app-id",
        mode="webhook",
        dm_policy="pairing",
        group_policy="open",
    )) is False


def test_t01_09_group_policy_uses_internal_wildcard(monkeypatch):
    _clear_env(monkeypatch)
    adapter._sync_auth_env_from_extra({
        "dm_policy": "allowlist",
        "allow_from": ["alice@example.com"],
        "group_policy": "open",
        "group_sender_allow_from": ["alice@example.com"],
    })

    assert adapter.os.environ["HERMES_SEATALK_ALLOWED_USERS"] == "*"


def test_t01_10_register_is_repeatable(monkeypatch):
    _clear_env(monkeypatch)
    ctx = FakeContext()

    adapter.register(ctx)
    adapter.register(ctx)

    assert [entry["name"] for entry in ctx.platforms] == ["seatalk"]
