from __future__ import annotations

import pytest

from hermes_seatalk.dispatcher import SeaTalkEventDispatcher


class FakeClient:
    async def download_media(self, _url):
        raise RuntimeError("download failed")


class FakeAdapter:
    def __init__(self):
        self.events = []

    async def handle_message(self, event):
        self.events.append(event)


def _dm_payload(event_id="event-1", text="hello", thread_id=None, email="Alice@Example.com"):
    message = {
        "message_id": f"msg-{event_id}",
        "tag": "text",
        "text": {"plain_text": text},
    }
    if thread_id:
        message["thread_id"] = thread_id
    return {
        "event_id": event_id,
        "event_type": "message_from_bot_subscriber",
        "app_id": "app-id",
        "event": {
            "employee_code": "EmpABC",
            "email": email,
            "message": message,
        },
    }


def _group_payload(event_id="event-1", text="hello", thread_id="ThreadABC", group_id="GroupABC"):
    message = {
        "message_id": f"msg-{event_id}",
        "thread_id": thread_id,
        "tag": "text",
        "text": {"plain_text": text},
        "sender": {
            "employee_code": "EmpABC",
            "email": "Alice@Example.com",
        },
    }
    return {
        "event_id": event_id,
        "event_type": "new_mentioned_message_received_from_group_chat",
        "app_id": "app-id",
        "event": {
            "group_id": group_id,
            "message": message,
        },
    }


def _dispatcher(fake_adapter=None, account_id="default", **kwargs):
    kwargs.setdefault("dm_policy", "open")
    kwargs.setdefault("group_policy", "open")
    return SeaTalkEventDispatcher(
        adapter=fake_adapter or FakeAdapter(),
        client=FakeClient(),
        app_id=f"app-{account_id}",
        account_id=account_id,
        debounce_idle_seconds=0,
        debounce_max_seconds=0,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_t2_03_01_dm_chat_id_has_account_prefix():
    fake_adapter = FakeAdapter()

    await _dispatcher(fake_adapter, account_id="default").dispatch(_dm_payload(), "relay")

    assert fake_adapter.events[0].source.chat_id == "default:EmpABC"


@pytest.mark.asyncio
async def test_t2_03_02_group_chat_id_has_account_prefix():
    fake_adapter = FakeAdapter()

    await _dispatcher(fake_adapter, account_id="staging").dispatch(_group_payload(), "relay")

    assert fake_adapter.events[0].source.chat_id == "staging:group/GroupABC"


@pytest.mark.asyncio
async def test_t2_03_03_user_id_has_no_account_prefix():
    fake_adapter = FakeAdapter()

    await _dispatcher(fake_adapter, account_id="default").dispatch(_dm_payload(), "relay")

    assert fake_adapter.events[0].source.user_id == "alice@example.com"
    assert not fake_adapter.events[0].source.user_id.startswith("default:")


@pytest.mark.asyncio
async def test_t2_03_04_thread_is_separate_from_chat_id():
    fake_adapter = FakeAdapter()

    await _dispatcher(fake_adapter, account_id="staging").dispatch(
        _group_payload(thread_id="ThreadXYZ"),
        "relay",
    )

    source = fake_adapter.events[0].source
    assert source.chat_id == "staging:group/GroupABC"
    assert source.thread_id == "ThreadXYZ"


@pytest.mark.asyncio
async def test_t2_03_05_raw_metadata_has_account_id():
    fake_adapter = FakeAdapter()

    await _dispatcher(fake_adapter, account_id="staging").dispatch(_dm_payload(), "relay")

    event = fake_adapter.events[0]
    assert event.raw_message["seatalk_account_id"] == "staging"
    assert event.raw_message["seatalk_events"][0]["seatalk_account_id"] == "staging"


@pytest.mark.asyncio
async def test_t2_03_06_session_key_isolated_by_account():
    session = pytest.importorskip("gateway.session")

    default_adapter = FakeAdapter()
    staging_adapter = FakeAdapter()
    await _dispatcher(default_adapter, account_id="default").dispatch(_dm_payload(event_id="default"), "relay")
    await _dispatcher(staging_adapter, account_id="staging").dispatch(_dm_payload(event_id="staging"), "relay")

    default_key = session.build_session_key(default_adapter.events[0].source)
    staging_key = session.build_session_key(staging_adapter.events[0].source)

    assert default_key != staging_key


@pytest.mark.asyncio
async def test_t2_03_07_dm_allowlist_matches_email_and_employee_code():
    email_adapter = FakeAdapter()
    employee_adapter = FakeAdapter()

    await _dispatcher(
        email_adapter,
        dm_policy="allowlist",
        allowlist={"alice@example.com"},
    ).dispatch(_dm_payload(event_id="email"), "relay")
    await _dispatcher(
        employee_adapter,
        dm_policy="allowlist",
        allowlist={"EmpABC"},
    ).dispatch(_dm_payload(event_id="employee"), "relay")

    assert len(email_adapter.events) == 1
    assert len(employee_adapter.events) == 1


@pytest.mark.asyncio
async def test_t2_03_08_group_allowlist_uses_raw_group_id():
    allowed_adapter = FakeAdapter()
    blocked_adapter = FakeAdapter()

    await _dispatcher(
        allowed_adapter,
        group_policy="allowlist",
        group_allowlist={"GroupABC"},
    ).dispatch(_group_payload(event_id="allowed"), "relay")
    await _dispatcher(
        blocked_adapter,
        group_policy="allowlist",
        group_allowlist={"group/GroupABC"},
    ).dispatch(_group_payload(event_id="blocked"), "relay")

    assert len(allowed_adapter.events) == 1
    assert blocked_adapter.events == []


@pytest.mark.asyncio
async def test_t2_03_09_group_sender_allowlist_applies_when_group_open():
    allowed_adapter = FakeAdapter()
    blocked_adapter = FakeAdapter()

    await _dispatcher(
        allowed_adapter,
        group_policy="open",
        group_sender_allowlist={"alice@example.com"},
    ).dispatch(_group_payload(event_id="allowed"), "relay")
    await _dispatcher(
        blocked_adapter,
        group_policy="open",
        group_sender_allowlist={"bob@example.com"},
    ).dispatch(_group_payload(event_id="blocked"), "relay")

    assert len(allowed_adapter.events) == 1
    assert blocked_adapter.events == []


@pytest.mark.asyncio
async def test_t2_03_10_account_policy_isolated():
    default_adapter = FakeAdapter()
    staging_adapter = FakeAdapter()

    await _dispatcher(
        default_adapter,
        account_id="default",
        dm_policy="allowlist",
        allowlist={"alice@example.com"},
    ).dispatch(_dm_payload(event_id="default"), "relay")
    await _dispatcher(
        staging_adapter,
        account_id="staging",
        dm_policy="allowlist",
        allowlist={"bob@example.com"},
    ).dispatch(_dm_payload(event_id="staging"), "relay")

    assert len(default_adapter.events) == 1
    assert staging_adapter.events == []
