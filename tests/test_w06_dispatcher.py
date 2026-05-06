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
    kwargs.setdefault("dm_policy", "open")
    kwargs.setdefault("group_policy", "open")
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
    session = pytest.importorskip("gateway.session")

    fake_adapter = FakeAdapter()
    dispatcher = _dispatcher(fake_adapter)

    await dispatcher.dispatch(_group_payload(event_id="event-1"), "webhook")
    await dispatcher.dispatch(_group_payload(event_id="event-2"), "relay")

    keys = [
        session.build_session_key(event.source, group_sessions_per_user=True, thread_sessions_per_user=False)
        for event in fake_adapter.events
    ]
    assert keys == [keys[0], keys[0]]


@pytest.mark.asyncio
async def test_t06_03_dedup(monkeypatch):
    fake_adapter = FakeAdapter()
    dispatcher = _dispatcher(fake_adapter)
    payload = _dm_payload(event_id="same-event")

    await dispatcher.dispatch(payload, "webhook")
    await dispatcher.dispatch(payload, "relay")

    assert len(fake_adapter.events) == 1


@pytest.mark.asyncio
async def test_t06_04_debounce_merge(monkeypatch):
    fake_adapter = FakeAdapter()
    dispatcher = SeaTalkEventDispatcher(
        adapter=fake_adapter,
        client=FakeClient(),
        app_id="app-id",
        dm_policy="open",
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


# ── Forwarded messages ────────────────────────────────────────────────────────

def _forwarded_payload(event_id="event-1", items=None):
    payload = _dm_payload(event_id=event_id, text="")
    payload["event"]["message"] = {
        "message_id": f"msg-{event_id}",
        "tag": "combined_forwarded_chat_history",
        "combined_forwarded_chat_history": {
            "content": items or [],
        },
    }
    return payload


@pytest.mark.asyncio
async def test_t06_07_forwarded_includes_media(monkeypatch):
    """Media from forwarded items must be included in event media_urls."""
    client = FakeClient()
    client.download_error = None  # disable auto-raise

    download_calls: list[str] = []

    async def _download(url):
        download_calls.append(url)
        return PNG_BYTES, "image/png"

    client.download_media = _download

    fake_adapter = FakeAdapter()
    items = [{"tag": "image", "image": {"content": "https://openapi.seatalk.io/media/img-1"}}]
    payload = _forwarded_payload(items=items)

    await _dispatcher(fake_adapter, client).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.media_urls != [], "media_urls should not be empty for forwarded image"
    assert "image" in event.media_types


@pytest.mark.asyncio
async def test_t06_08_forwarded_sender_prefix(monkeypatch):
    """Each forwarded item with a sender field gets a 'SenderName: ' prefix."""
    fake_adapter = FakeAdapter()
    items = [
        {
            "tag": "text",
            "text": {"plain_text": "hello from alice"},
            "sender": {"employee_code": "EmpAlice", "email": "alice@example.com"},
        },
        {
            "tag": "text",
            "text": {"plain_text": "hi from bob"},
            "sender": {"employee_code": "EmpBob"},
        },
    ]
    payload = _forwarded_payload(items=items)

    await _dispatcher(fake_adapter).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert "EmpAlice (alice@example.com): hello from alice" in event.text
    assert "EmpBob: hi from bob" in event.text


@pytest.mark.asyncio
async def test_t06_09_forwarded_nested_array(monkeypatch):
    """content list may contain nested lists; they should be recursively expanded."""
    fake_adapter = FakeAdapter()
    inner_item = {"tag": "text", "text": {"plain_text": "nested text"}}
    items = [[inner_item]]  # list-of-list
    payload = _forwarded_payload(items=items)

    await _dispatcher(fake_adapter).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert "nested text" in event.text


@pytest.mark.asyncio
async def test_t06_10_quoted_dedup_same_id_in_buffer(monkeypatch):
    """Two messages in same debounce window quoting the same id → quoted text appears once."""
    client = FakeClient()
    client.quoted["q1"] = {
        "tag": "text",
        "text": {"plain_text": "the quote"},
        "sender": {"employee_code": "Sender"},
    }

    fake_adapter = FakeAdapter()
    dispatcher = SeaTalkEventDispatcher(
        adapter=fake_adapter,
        client=client,
        app_id="app-id",
        dm_policy="open",
        debounce_idle_seconds=60,
        debounce_max_seconds=60,
    )

    p1 = _dm_payload(event_id="ev-1", text="reply1")
    p1["event"]["message"]["quoted_message_id"] = "q1"
    p2 = _dm_payload(event_id="ev-2", text="reply2")
    p2["event"]["message"]["quoted_message_id"] = "q1"

    await dispatcher.dispatch(p1, "webhook")
    await dispatcher.dispatch(p2, "webhook")
    await dispatcher.flush_all()

    assert len(fake_adapter.events) == 1
    event = fake_adapter.events[0]
    # The quoted text block should appear exactly once
    assert event.text.count("[Quoted from Sender: the quote]") == 1
    assert "reply1" in event.text
    assert "reply2" in event.text


@pytest.mark.asyncio
async def test_t06_11_quoted_no_dedup_different_ids(monkeypatch):
    """Two messages with different quoted_message_ids → both quoted texts appear."""
    client = FakeClient()
    client.quoted["q1"] = {
        "tag": "text",
        "text": {"plain_text": "first quote"},
        "sender": {"employee_code": "S1"},
    }
    client.quoted["q2"] = {
        "tag": "text",
        "text": {"plain_text": "second quote"},
        "sender": {"employee_code": "S2"},
    }

    fake_adapter = FakeAdapter()
    dispatcher = SeaTalkEventDispatcher(
        adapter=fake_adapter,
        client=client,
        app_id="app-id",
        dm_policy="open",
        debounce_idle_seconds=60,
        debounce_max_seconds=60,
    )

    p1 = _dm_payload(event_id="ev-1", text="reply1")
    p1["event"]["message"]["quoted_message_id"] = "q1"
    p2 = _dm_payload(event_id="ev-2", text="reply2")
    p2["event"]["message"]["quoted_message_id"] = "q2"

    await dispatcher.dispatch(p1, "webhook")
    await dispatcher.dispatch(p2, "webhook")
    await dispatcher.flush_all()

    event = fake_adapter.events[0]
    assert "[Quoted from S1: first quote]" in event.text
    assert "[Quoted from S2: second quote]" in event.text


@pytest.mark.asyncio
async def test_t06_12_media_retry_succeeds_on_second_attempt(monkeypatch):
    """Media download fails on first attempt but succeeds on second → media in result."""
    client = FakeClient()
    attempt_count = {"n": 0}

    async def _flaky_download(url):
        attempt_count["n"] += 1
        if attempt_count["n"] == 1:
            raise RuntimeError("transient error")
        return PNG_BYTES, "image/png"

    client.download_media = _flaky_download
    client.download_error = None

    fake_adapter = FakeAdapter()
    payload = _dm_payload(event_id="event-1", text="")
    payload["event"]["message"] = {
        "message_id": "msg-media",
        "tag": "image",
        "image": {"content": "https://openapi.seatalk.io/media/image-1"},
    }

    await _dispatcher(fake_adapter, client).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.media_urls != [], "media should be present after successful retry"
    assert event.raw_message["seatalk_media_errors"] == []
    assert attempt_count["n"] == 2
