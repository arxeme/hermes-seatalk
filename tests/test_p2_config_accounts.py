from __future__ import annotations

from types import SimpleNamespace

import pytest

from hermes_seatalk import adapter


def _config(*, enabled: bool = True, **extra):
    return SimpleNamespace(enabled=enabled, extra=extra)


def _relay_account(**overrides):
    account = {
        "enabled": True,
        "app_id": "app-default",
        "app_secret": "secret-default",
        "signing_secret": "sign-default",
        "mode": "relay",
        "relay_url": "wss://relay.example/ws",
    }
    account.update(overrides)
    return account


def _webhook_account(**overrides):
    account = {
        "enabled": True,
        "app_id": "app-webhook",
        "app_secret": "secret-webhook",
        "signing_secret": "sign-webhook",
        "mode": "webhook",
    }
    account.update(overrides)
    return account


@pytest.mark.parametrize("accounts", [None, {}, [], "default"])
def test_t2_00_01_accounts_missing_fails(accounts):
    extra = {} if accounts is None else {"accounts": accounts}

    assert adapter._validate_seatalk_config(_config(**extra)) is False


def test_t2_00_02_enabled_false_handling():
    assert adapter._validate_seatalk_config(_config(enabled=False)) is True

    cfg = _config(
        accounts={
            "disabled": {"enabled": False},
            "default": _relay_account(),
        },
    )

    assert adapter._validate_seatalk_config(cfg) is True
    assert list(adapter._accounts_from_extra(cfg.extra)) == ["default"]


def test_t2_00_03_top_level_default_merge():
    cfg = _config(
        dm_policy="allowlist",
        allow_from=["alice@example.com"],
        group_policy="disabled",
        processing_indicator="typing",
        accounts={
            "default": _relay_account(group_policy="open"),
            "staging": _webhook_account(app_id="app-staging"),
        },
    )

    accounts = adapter._accounts_from_extra(cfg.extra)

    assert accounts["default"].dm_policy == "allowlist"
    assert accounts["default"].allow_from == ("alice@example.com",)
    assert accounts["default"].group_policy == "open"
    assert accounts["staging"].group_policy == "disabled"
    assert accounts["staging"].processing_indicator == "typing"


@pytest.mark.parametrize("missing", ["app_id", "app_secret", "signing_secret", "mode"])
def test_t2_00_04_credentials_completeness(missing):
    account = _relay_account()
    account.pop(missing)

    assert adapter._validate_seatalk_config(_config(accounts={"default": account})) is False


def test_t2_00_05_relay_required_fields():
    account = _relay_account()
    account.pop("relay_url")

    assert adapter._validate_seatalk_config(_config(accounts={"default": account})) is False


@pytest.mark.parametrize("field,value", [
    ("webhook_port", "not-a-port"),
    ("webhook_port", 0),
    ("webhook_port", 65536),
    ("webhook_path", "callback"),
    ("webhook_path", "/bad path"),
])
def test_t2_00_06_webhook_validation(field, value):
    assert adapter._validate_seatalk_config(
        _config(accounts={"default": _webhook_account(**{field: value})})
    ) is False


@pytest.mark.parametrize("account_id", ["", "Default", ":default", "team/a", "team a", "-team"])
def test_t2_00_07_account_id_validation(account_id):
    assert adapter._validate_seatalk_config(
        _config(accounts={account_id: _relay_account()})
    ) is False


def test_t2_00_08_duplicate_app_id():
    assert adapter._validate_seatalk_config(
        _config(accounts={
            "default": _relay_account(app_id="same"),
            "staging": _webhook_account(app_id="same"),
        })
    ) is False


@pytest.mark.parametrize("field,value", [
    ("dm_policy", "everyone"),
    ("dm_policy", "pairing"),
    ("group_policy", "everyone"),
    ("processing_indicator", "spinner"),
])
def test_t2_00_09_policy_enum(field, value):
    assert adapter._validate_seatalk_config(
        _config(accounts={"default": _relay_account(**{field: value})})
    ) is False


def test_t2_00_10_group_id_format():
    assert adapter._validate_seatalk_config(
        _config(accounts={"default": _relay_account(group_allow_from=["group/GroupABC"])})
    ) is False


def test_t2_00_11_env_secrets_do_not_participate(monkeypatch):
    monkeypatch.delenv("SEATALK_APP_SECRET", raising=False)
    monkeypatch.delenv("SEATALK_SIGNING_SECRET", raising=False)

    assert adapter._validate_seatalk_config(
        _config(accounts={"default": _relay_account()})
    ) is True

