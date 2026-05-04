from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("gateway", reason="requires Hermes gateway")

from gateway.config import Platform  # noqa: E402
from gateway.platform_registry import PlatformEntry, platform_registry  # noqa: E402
from gateway.run import GatewayRunner  # noqa: E402
from gateway.session import SessionSource  # noqa: E402

from hermes_seatalk.dispatcher import SeaTalkEventDispatcher  # noqa: E402

pytestmark = pytest.mark.requires_hermes


class FakePairingStore:
    def is_approved(self, _platform, _user_id):
        return False


class FakeAdapter:
    def __init__(self):
        self.events = []

    async def handle_message(self, event):
        self.events.append(event)


class FakeClient:
    async def get_message_by_id(self, _message_id):
        raise AssertionError("not used")


def _register_seatalk_auth_entry():
    if platform_registry.is_registered("seatalk"):
        return
    platform_registry.register(PlatformEntry(
        name="seatalk",
        label="SeaTalk",
        adapter_factory=lambda cfg: None,
        check_fn=lambda: True,
        allowed_users_env="SEATALK_ALLOWED_USERS",
        allow_all_env="SEATALK_ALLOW_ALL_USERS",
    ))


def _gateway_auth(source: SessionSource) -> bool:
    _register_seatalk_auth_entry()
    runner = SimpleNamespace(pairing_store=FakePairingStore())
    return GatewayRunner._is_user_authorized(runner, source)


def _source(user_id, user_id_alt="EmpABC", chat_type="dm", chat_id="EmpABC"):
    _register_seatalk_auth_entry()
    return SessionSource(
        platform=Platform("seatalk"),
        chat_id=chat_id,
        chat_type=chat_type,
        user_id=user_id,
        user_name=user_id,
        user_id_alt=user_id_alt,
    )


def _group_payload(group_id="GroupABC", email="Alice@Example.com"):
    return {
        "event_id": "event-1",
        "event_type": "new_mentioned_message_received_from_group_chat",
        "app_id": "app-id",
        "event": {
            "group_id": group_id,
            "message": {
                "message_id": "msg-1",
                "tag": "text",
                "text": {"plain_text": "hello"},
                "sender": {
                    "employee_code": "EmpABC",
                    "email": email,
                },
            },
        },
    }


def _dm_payload(email="Alice@Example.com"):
    return {
        "event_id": "event-1",
        "event_type": "message_from_bot_subscriber",
        "app_id": "app-id",
        "event": {
            "employee_code": "EmpABC",
            "email": email,
            "message": {
                "message_id": "msg-1",
                "tag": "text",
                "text": {"plain_text": "hello"},
            },
        },
    }


async def _dispatch(payload):
    fake_adapter = FakeAdapter()
    dispatcher = SeaTalkEventDispatcher(
        adapter=fake_adapter,
        client=FakeClient(),
        app_id="app-id",
        debounce_idle_seconds=0,
        debounce_max_seconds=0,
    )
    await dispatcher.dispatch(payload, "webhook")
    return fake_adapter.events


@pytest.mark.asyncio
async def test_t07_01_email_priority(monkeypatch):
    monkeypatch.delenv("SEATALK_GROUP_ALLOWED_USERS", raising=False)
    events = await _dispatch(_dm_payload(email="Alice@Example.com"))

    source = events[0].source
    assert source.user_id == "alice@example.com"
    assert source.user_id_alt == "EmpABC"

    monkeypatch.setenv("SEATALK_ALLOWED_USERS", "alice@example.com")
    monkeypatch.delenv("SEATALK_ALLOW_ALL_USERS", raising=False)
    monkeypatch.delenv("GATEWAY_ALLOWED_USERS", raising=False)
    monkeypatch.delenv("GATEWAY_ALLOW_ALL_USERS", raising=False)
    assert _gateway_auth(source) is True


@pytest.mark.asyncio
async def test_t07_02_employee_fallback(monkeypatch):
    monkeypatch.delenv("SEATALK_GROUP_ALLOWED_USERS", raising=False)
    events = await _dispatch(_dm_payload(email=None))

    source = events[0].source
    assert source.user_id == "EmpABC"
    assert source.user_id_alt == "EmpABC"

    monkeypatch.setenv("SEATALK_ALLOWED_USERS", "EmpABC")
    monkeypatch.delenv("SEATALK_ALLOW_ALL_USERS", raising=False)
    monkeypatch.delenv("GATEWAY_ALLOWED_USERS", raising=False)
    monkeypatch.delenv("GATEWAY_ALLOW_ALL_USERS", raising=False)
    assert _gateway_auth(source) is True


def test_t07_03_unauthorized_user_rejected(monkeypatch):
    monkeypatch.setenv("SEATALK_ALLOWED_USERS", "bob@example.com")
    monkeypatch.delenv("SEATALK_ALLOW_ALL_USERS", raising=False)
    monkeypatch.delenv("GATEWAY_ALLOWED_USERS", raising=False)
    monkeypatch.delenv("GATEWAY_ALLOW_ALL_USERS", raising=False)

    assert _gateway_auth(_source("alice@example.com")) is False


@pytest.mark.asyncio
async def test_t07_04_group_allowlist_pass(monkeypatch):
    monkeypatch.setenv("SEATALK_GROUP_ALLOWED_USERS", "group/GroupABC")

    events = await _dispatch(_group_payload(group_id="GroupABC"))

    assert len(events) == 1
    assert events[0].source.chat_id == "group/GroupABC"


@pytest.mark.asyncio
async def test_t07_05_group_allowlist_reject(monkeypatch):
    monkeypatch.setenv("SEATALK_GROUP_ALLOWED_USERS", "group/Allowed")

    events = await _dispatch(_group_payload(group_id="Denied"))

    assert events == []


@pytest.mark.asyncio
async def test_t07_06_rejection_log_redacted(monkeypatch, caplog):
    monkeypatch.setenv("SEATALK_GROUP_ALLOWED_USERS", "group/Allowed")
    monkeypatch.setenv("SEATALK_APP_SECRET", "super-secret-token")

    events = await _dispatch(_group_payload(group_id="Denied"))

    assert events == []
    logs = caplog.text
    assert "group/Denied" in logs
    assert "group_not_allowed" in logs
    assert "super-secret-token" not in logs
    assert "Alice@Example.com" not in logs
