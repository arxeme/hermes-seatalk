from __future__ import annotations

import sys
import pytest
from types import ModuleType, SimpleNamespace

from hermes_seatalk import adapter


SEATALK_ENV = [
    "SEATALK_APP_SECRET",
    "SEATALK_SIGNING_SECRET",
    "HERMES_SEATALK_ALLOW_ALL",
    "SEATALK_HOME_CHANNEL",
    "SEATALK_HOME_CHANNEL_THREAD_ID",
]


class FakeContext:
    def __init__(self):
        self.platforms = []
        self.tools = []

    def register_platform(self, **kwargs):
        self.platforms.append(kwargs)

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)


def _clear_env(monkeypatch):
    for name in SEATALK_ENV:
        monkeypatch.delenv(name, raising=False)


def _set_aiohttp_available(monkeypatch):
    monkeypatch.setitem(sys.modules, "aiohttp", ModuleType("aiohttp"))


def _set_config_file_extra(monkeypatch, **extra):
    monkeypatch.setattr(adapter, "_config_file_extra", lambda: extra)


def _config(**extra):
    return SimpleNamespace(enabled=True, extra=extra)


def _relay_account(**overrides):
    account = {
        "enabled": True,
        "app_id": "app-id",
        "app_secret": "app-secret",
        "signing_secret": "signing-secret",
        "mode": "relay",
        "relay_url": "wss://relay.example/ws",
    }
    account.update(overrides)
    return account


def _webhook_account(**overrides):
    account = {
        "enabled": True,
        "app_id": "app-id",
        "app_secret": "app-secret",
        "signing_secret": "signing-secret",
        "mode": "webhook",
    }
    account.update(overrides)
    return account


def test_t01_01_minimal_relay_config_registers_platform(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)
    _set_config_file_extra(monkeypatch, accounts={"default": _relay_account()})

    ctx = FakeContext()
    adapter.register(ctx)

    assert len(ctx.platforms) == 1
    entry = ctx.platforms[0]
    assert entry["name"] == "seatalk"
    assert entry["label"] == "SeaTalk"
    assert entry["check_fn"] is adapter.check_seatalk_requirements
    assert entry["validate_config"] is adapter._validate_seatalk_config
    assert entry["is_connected"] is adapter._is_seatalk_connected
    assert entry["required_env"] == []
    assert "allowed_users_env" not in entry
    assert entry["allow_all_env"] == "HERMES_SEATALK_ALLOW_ALL"
    assert entry["max_message_length"] == 4000
    assert adapter.os.environ["HERMES_SEATALK_ALLOW_ALL"] == "true"
    assert "HERMES_SEATALK_ALLOWED_USERS" not in adapter.os.environ
    assert "SEATALK_HOME_CHANNEL" not in adapter.os.environ


def test_t01_02_missing_credentials_fail(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)
    monkeypatch.setattr(adapter, "_config_file_extra", lambda: (_ for _ in ()).throw(AssertionError("must not read config")))

    assert adapter.check_seatalk_requirements() is True
    assert adapter._validate_seatalk_config(_config(
        accounts={"default": _webhook_account(signing_secret="")},
    )) is False


def test_t01_03_relay_url_required_only_for_relay(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)

    assert adapter._validate_seatalk_config(_config(
        accounts={"default": _relay_account(relay_url="")},
    )) is False
    assert adapter._validate_seatalk_config(_config(
        accounts={"default": _relay_account()},
    )) is True


def test_t01_04_webhook_does_not_require_relay_url(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)

    assert adapter._validate_seatalk_config(_config(
        accounts={"default": _webhook_account()},
    )) is True


def test_t01_05_is_connected_matches_validate_config(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)
    cfg = _config(accounts={"default": _webhook_account()})

    assert adapter._is_seatalk_connected(cfg) is adapter._validate_seatalk_config(cfg)


def test_t01_06_runtime_health_does_not_affect_connected(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)
    cfg = _config(accounts={"default": _webhook_account()})

    assert adapter._is_seatalk_connected(cfg) is True


def test_t01_07_invalid_mode_is_rejected(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)

    assert adapter._validate_seatalk_config(_config(
        accounts={"default": _relay_account(mode="socket")},
    )) is False


def test_t01_08_invalid_policy_is_rejected(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)

    assert adapter._validate_seatalk_config(_config(
        accounts={"default": _webhook_account(dm_policy="everyone")},
    )) is False
    assert adapter._validate_seatalk_config(_config(
        accounts={"default": _webhook_account(group_policy="everyone")},
    )) is False
    assert adapter._validate_seatalk_config(_config(
        accounts={"default": _webhook_account(processing_indicator="spinner")},
    )) is False
    assert adapter._validate_seatalk_config(_config(
        accounts={"default": _webhook_account(dm_policy="pairing")},
    )) is False


def test_t01_09_register_does_not_write_user_allowlists(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)
    _set_config_file_extra(
        monkeypatch,
        dm_policy="open",
        allow_from=["alice@example.com"],
        accounts={"default": _relay_account()},
    )

    adapter.register(FakeContext())

    assert adapter.os.environ["HERMES_SEATALK_ALLOW_ALL"] == "true"
    assert "HERMES_SEATALK_ALLOWED_USERS" not in adapter.os.environ


def test_t01_10_register_is_repeatable(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)
    ctx = FakeContext()

    adapter.register(ctx)
    adapter.register(ctx)

    assert [entry["name"] for entry in ctx.platforms] == ["seatalk"]
    assert len(ctx.tools) == 1


def test_t01_11_seatalk_tool_registered(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)
    _set_config_file_extra(monkeypatch, accounts={"default": _relay_account()})

    ctx = FakeContext()
    adapter.register(ctx)

    assert len(ctx.tools) == 1
    tool = ctx.tools[0]
    assert tool["name"] == "seatalk_query"
    assert tool["toolset"] == "seatalk-platform"
    assert tool["is_async"] is True
    assert callable(tool["handler"])


def test_t01_12_seatalk_tool_skipped_without_register_tool(monkeypatch):
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)

    class MinimalContext:
        def __init__(self):
            self.platforms = []
        def register_platform(self, **kwargs):
            self.platforms.append(kwargs)

    ctx = MinimalContext()
    adapter.register(ctx)

    assert len(ctx.platforms) == 1


def test_t01_13_no_accounts_key_passes_validation(monkeypatch):
    """Plugin installed but not configured: validate_config returns True (skip gracefully)."""
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)

    assert adapter._validate_seatalk_config(_config()) is True
    assert adapter._is_seatalk_connected(_config()) is True


@pytest.mark.asyncio
async def test_t01_14_unconfigured_adapter_connects_and_rejects_send(monkeypatch):
    """No accounts: connect() succeeds but send() returns a clear error."""
    _clear_env(monkeypatch)
    _set_aiohttp_available(monkeypatch)

    seatalk = adapter.SeaTalkAdapter(_config())
    assert await seatalk.connect() is True

    result = await seatalk.send("EmpABC", "hello")
    assert result.success is False
    assert "no accounts" in result.error.lower() or "not configured" in result.error.lower()

    await seatalk.disconnect()
