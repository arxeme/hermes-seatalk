from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from hermes_seatalk import adapter


class FakeOpenAPIClient:
    instances = []

    def __init__(self, app_id, app_secret, *, log_secrets=None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.log_secrets = tuple(log_secrets or ())
        self.closed = False
        FakeOpenAPIClient.instances.append(self)

    async def close(self):
        self.closed = True


def _config(**extra):
    return SimpleNamespace(enabled=True, extra=extra)


def _relay_account(app_id, **overrides):
    account = {
        "enabled": True,
        "app_id": app_id,
        "app_secret": f"{app_id}-secret",
        "signing_secret": f"{app_id}-signing",
        "mode": "relay",
        "relay_url": f"wss://relay.example/{app_id}",
    }
    account.update(overrides)
    return account


def _accounts_extra():
    return {
        "accounts": {
            "default": _relay_account("app-default"),
            "staging": _relay_account("app-staging"),
            "disabled": {"enabled": False},
        },
    }


@pytest.fixture(autouse=True)
def _fake_client(monkeypatch):
    FakeOpenAPIClient.instances = []
    monkeypatch.setattr(adapter, "SeaTalkOpenAPIClient", FakeOpenAPIClient)


def test_t2_02_01_runtime_map_creation():
    seatalk = adapter.SeaTalkAdapter(_config(**_accounts_extra()))

    assert set(seatalk.accounts) == {"default", "staging"}
    assert set(seatalk._runtimes) == {"default", "staging"}
    assert seatalk._default_account_id == "default"


def test_t2_02_02_runtime_isolation():
    seatalk = adapter.SeaTalkAdapter(_config(**_accounts_extra()))
    default = seatalk._runtimes["default"]
    staging = seatalk._runtimes["staging"]

    assert default.client is not staging.client
    assert default.dispatcher is not staging.dispatcher
    assert default.coalescers is not staging.coalescers
    assert default.config.app_id == "app-default"
    assert staging.config.app_id == "app-staging"


def test_t2_02_03_secret_cross_account_redaction():
    adapter.SeaTalkAdapter(_config(**_accounts_extra()))

    expected = {
        "app-default-secret",
        "app-default-signing",
        "app-staging-secret",
        "app-staging-signing",
    }
    assert FakeOpenAPIClient.instances
    for client in FakeOpenAPIClient.instances:
        assert set(client.log_secrets) == expected


def test_t2_02_04_state_fields():
    seatalk = adapter.SeaTalkAdapter(_config(**_accounts_extra()))
    runtime = seatalk._runtimes["default"]

    assert runtime.state == "stopped"
    assert runtime.auth_failed is False
    assert runtime.last_error is None

    seatalk._set_runtime_state(runtime, "auth_failed", "bad credentials")

    assert runtime.state == "auth_failed"
    assert runtime.auth_failed is True
    assert runtime.last_error == "bad credentials"


def test_t2_02_05_single_account_permanent_failure_isolated():
    seatalk = adapter.SeaTalkAdapter(_config(**_accounts_extra()))
    marks = []
    seatalk._mark_running = lambda: marks.append("running")
    seatalk._mark_fatal = lambda code, message, retryable=False: marks.append(("fatal", code, message))

    seatalk._set_runtime_state(seatalk._runtimes["default"], "auth_failed", "bad credentials")
    seatalk._set_runtime_state(seatalk._runtimes["staging"], "running")
    seatalk._refresh_platform_state()

    assert marks == ["running"]


def test_t2_02_06_aggregation_non_fatal_when_retrying():
    seatalk = adapter.SeaTalkAdapter(_config(**_accounts_extra()))
    marks = []
    seatalk._mark_running = lambda: marks.append("running")
    seatalk._mark_fatal = lambda code, message, retryable=False: marks.append(("fatal", code, message))

    seatalk._set_runtime_state(seatalk._runtimes["default"], "auth_failed", "bad credentials")
    seatalk._set_runtime_state(seatalk._runtimes["staging"], "retrying", "network")
    seatalk._refresh_platform_state()

    assert marks == ["running"]


def test_t2_02_07_aggregation_fatal_when_all_permanently_failed():
    seatalk = adapter.SeaTalkAdapter(_config(**_accounts_extra()))
    marks = []
    seatalk._mark_running = lambda: marks.append("running")
    seatalk._mark_fatal = lambda code, message, retryable=False: marks.append(("fatal", code, message))

    for runtime in seatalk._runtimes.values():
        seatalk._set_runtime_state(runtime, "auth_failed", "bad credentials")
    seatalk._refresh_platform_state()

    assert marks == [("fatal", "seatalk_all_accounts_failed", "all SeaTalk accounts failed")]


@pytest.mark.asyncio
async def test_t2_02_08_disconnect_all_runtimes():
    seatalk = adapter.SeaTalkAdapter(_config(**_accounts_extra()))

    await seatalk.disconnect()

    assert all(runtime.state == "stopped" for runtime in seatalk._runtimes.values())
    assert all(client.closed for client in FakeOpenAPIClient.instances)


def test_t2_02_09_account_id_logs(caplog):
    seatalk = adapter.SeaTalkAdapter(_config(**_accounts_extra()))

    with caplog.at_level(logging.INFO, logger="hermes_seatalk.adapter"):
        seatalk._set_runtime_state(seatalk._runtimes["staging"], "retrying", "network")

    assert "account_id=staging" in caplog.text
    assert "state=retrying" in caplog.text

