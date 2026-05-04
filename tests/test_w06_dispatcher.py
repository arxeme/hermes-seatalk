from __future__ import annotations

import pytest

from hermes_seatalk.dispatcher import SeaTalkEventDispatcher


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeClient:
    def __init__(self):
        self.quoted = {}
        self.download_error = RuntimeError("download failed")

    async def get_message_by_id(self, message_id):
        return self.quoted[message_id]

    async def download_media(self, _url):
        raise self.download_error


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


def _dispatcher(fake_adapter=None, fake_client=None, **kwargs):
    return SeaTalkEventDispatcher(
        adapter=fake_adapter or FakeAdapter(),
        client=fake_client or FakeClient(),
        app_id="app-id",
        debounce_idle_seconds=0,
        debounce_max_seconds=0,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_t06_01_webhook_relay_isomorphic(monkeypatch):
    monkeypatch.delenv("SEATALK_GROUP_ALLOWED_USERS", raising=False)
    webhook_adapter = FakeAdapter()
    relay_adapter = FakeAdapter()

    await _dispatcher(webhook_adapter).dispatch(_group_payload(event_id="webhook-event"), "webhook")
    await _dispatcher(relay_adapter).dispatch(_group_payload(event_id="relay-event"), "relay")

    webhook_event = webhook_adapter.events[0]
    relay_event = relay_adapter.events[0]
    assert webhook_event.text == relay_event.text
    assert webhook_event.source.chat_id == relay_event.source.chat_id
    assert webhook_event.source.thread_id == relay_event.source.thread_id
    assert webhook_event.source.user_id == relay_event.source.user_id
    assert webhook_event.source.user_id_alt == relay_event.source.user_id_alt


@pytest.mark.asyncio
@pytest.mark.requires_hermes
async def test_t06_02_session_key_stable(monkeypatch):
    from gateway.session import build_session_key

    monkeypatch.delenv("SEATALK_GROUP_ALLOWED_USERS", raising=False)
    fake_adapter = FakeAdapter()
    dispatcher = _dispatcher(fake_adapter)

    await dispatcher.dispatch(_group_payload(event_id="event-1"), "webhook")
    await dispatcher.dispatch(_group_payload(event_id="event-2"), "relay")

    keys = [
        build_session_key(event.source, group_sessions_per_user=True, thread_sessions_per_user=False)
        for event in fake_adapter.events
    ]
    assert keys == [keys[0], keys[0]]


@pytest.mark.asyncio
async def test_t06_03_dedup(monkeypatch):
    monkeypatch.delenv("SEATALK_GROUP_ALLOWED_USERS", raising=False)
    fake_adapter = FakeAdapter()
    dispatcher = _dispatcher(fake_adapter)
    payload = _dm_payload(event_id="same-event")

    await dispatcher.dispatch(payload, "webhook")
    await dispatcher.dispatch(payload, "relay")

    assert len(fake_adapter.events) == 1


@pytest.mark.asyncio
async def test_t06_04_debounce_merge(monkeypatch):
    monkeypatch.delenv("SEATALK_GROUP_ALLOWED_USERS", raising=False)
    fake_adapter = FakeAdapter()
    dispatcher = SeaTalkEventDispatcher(
        adapter=fake_adapter,
        client=FakeClient(),
        app_id="app-id",
        debounce_idle_seconds=60,
        debounce_max_seconds=60,
    )

    await dispatcher.dispatch(_dm_payload(event_id="event-1", text="one"), "webhook")
    await dispatcher.dispatch(_dm_payload(event_id="event-2", text="two"), "webhook")
    assert fake_adapter.events == []

    await dispatcher.flush_all()

    assert len(fake_adapter.events) == 1
    assert fake_adapter.events[0].text == "one\ntwo"


@pytest.mark.asyncio
async def test_t06_05_quoted_message(monkeypatch):
    monkeypatch.delenv("SEATALK_GROUP_ALLOWED_USERS", raising=False)
    client = FakeClient()
    client.quoted["quoted-1"] = {
        "tag": "text",
        "text": {"plain_text": "quoted text"},
        "sender": {"employee_code": "QuotedEmp", "email": "quoted@example.com"},
    }
    fake_adapter = FakeAdapter()
    payload = _dm_payload(event_id="event-1", text="reply")
    payload["event"]["message"]["quoted_message_id"] = "quoted-1"

    await _dispatcher(fake_adapter, client).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.reply_to_message_id == "quoted-1"
    assert event.reply_to_text == "[Quoted from QuotedEmp (quoted@example.com): quoted text]"
    assert event.text == "[Quoted from QuotedEmp (quoted@example.com): quoted text]\nreply"


@pytest.mark.asyncio
async def test_t06_06_attachment_failure_degrades(monkeypatch):
    monkeypatch.delenv("SEATALK_GROUP_ALLOWED_USERS", raising=False)
    fake_adapter = FakeAdapter()
    payload = _dm_payload(event_id="event-1", text="")
    payload["event"]["message"] = {
        "message_id": "msg-media",
        "tag": "image",
        "image": {"content": "https://openapi.seatalk.io/media/image-1"},
    }

    await _dispatcher(fake_adapter).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.text == "<media:image>"
    assert event.media_urls == []
    assert "download failed" in event.raw_message["seatalk_media_errors"][0]
