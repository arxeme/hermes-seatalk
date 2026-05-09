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
    assert "image/png" in event.media_types


@pytest.mark.asyncio
async def test_t06_08_forwarded_sender_prefix(monkeypatch):
    """Each forwarded item with a sender uses [sender] bracket prefix."""
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
    # email takes precedence over code in bracket prefix
    assert "[alice@example.com] hello from alice" in event.text
    assert "[EmpBob] hi from bob" in event.text


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


# ── Fix 1: forwarded sender prefix with timestamp ────────────────────────────


@pytest.mark.asyncio
async def test_t06_13_forwarded_sender_prefix_with_timestamp(monkeypatch):
    """message_sent_time is included in the forwarded item sender prefix."""
    fake_adapter = FakeAdapter()
    items = [
        {
            "tag": "text",
            "text": {"plain_text": "msg with time"},
            "sender": {"employee_code": "EmpAlice", "email": "alice@example.com"},
            "message_sent_time": 1735689600,  # 2025-01-01T00:00:00Z
        },
        {
            "tag": "text",
            "text": {"plain_text": "msg code only with time"},
            "sender": {"employee_code": "EmpBob"},
            "message_sent_time": 1735689600,
        },
        {
            "tag": "text",
            "text": {"plain_text": "no sender at all"},
        },
    ]
    payload = _forwarded_payload(items=items)
    await _dispatcher(fake_adapter).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert "[alice@example.com 2025-01-01T00:00:00Z] msg with time" in event.text
    assert "[EmpBob 2025-01-01T00:00:00Z] msg code only with time" in event.text
    assert "no sender at all" in event.text


def test_t06_14_format_forwarded_sender_prefix_unit():
    """Unit-test _format_forwarded_sender_prefix helper directly."""
    from hermes_seatalk.dispatcher import _format_forwarded_sender_prefix

    assert _format_forwarded_sender_prefix({}) == ""
    assert _format_forwarded_sender_prefix({"sender": {}}) == ""

    r = _format_forwarded_sender_prefix({"sender": {"email": "a@b.com"}})
    assert r == "[a@b.com] "

    r = _format_forwarded_sender_prefix({"sender": {"employee_code": "EmpX"}})
    assert r == "[EmpX] "

    r = _format_forwarded_sender_prefix({
        "sender": {"email": "a@b.com"},
        "message_sent_time": 1735689600,
    })
    assert r == "[a@b.com 2025-01-01T00:00:00Z] "

    # zero / negative sent_time is ignored
    r = _format_forwarded_sender_prefix({
        "sender": {"email": "a@b.com"},
        "message_sent_time": 0,
    })
    assert r == "[a@b.com] "


# ── Fix 2: buffer-based MIME detection ───────────────────────────────────────


def test_t06_15_detect_mime_from_buffer_unit():
    """Unit-test _detect_mime_from_buffer for common formats."""
    from hermes_seatalk.dispatcher import _detect_mime_from_buffer

    assert _detect_mime_from_buffer(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8) == "image/png"
    assert _detect_mime_from_buffer(b"\xff\xd8\xff\xe0" + b"\x00" * 8) == "image/jpeg"
    assert _detect_mime_from_buffer(b"GIF89a" + b"\x00" * 8) == "image/gif"
    assert _detect_mime_from_buffer(b"GIF87a" + b"\x00" * 8) == "image/gif"
    assert _detect_mime_from_buffer(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8) == "image/webp"
    assert _detect_mime_from_buffer(b"%PDF-1.4" + b"\x00" * 8) == "application/pdf"
    assert _detect_mime_from_buffer(b"PK\x03\x04" + b"\x00" * 8) == "application/zip"
    assert _detect_mime_from_buffer(b"\x00\x00\x00\x18ftyp" + b"\x00" * 8) == "video/mp4"
    assert _detect_mime_from_buffer(b"\x00\x00\x00\x00" + b"\x00" * 8) is None


@pytest.mark.asyncio
async def test_t06_16_mime_detection_applied_when_octet_stream(monkeypatch):
    """When server returns application/octet-stream with no URL extension, buffer MIME is used."""
    client = FakeClient()
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

    async def _download(_url):
        return png_bytes, "application/octet-stream"

    client.download_media = _download
    client.download_error = None

    fake_adapter = FakeAdapter()
    payload = _dm_payload(event_id="event-1", text="")
    payload["event"]["message"] = {
        "message_id": "msg-1",
        "tag": "image",
        # URL has no extension so Path(parsed.path).suffix == ""
        "image": {"content": "https://openapi.seatalk.io/media/abc123"},
    }

    await _dispatcher(fake_adapter, client).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.media_urls != [], "media should be resolved via buffer MIME detection"
    assert "image/png" in event.media_types


# ── Fix 4: inbound media size limit ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_t06_17_inbound_media_size_limit_rejected(monkeypatch):
    """Media larger than 250 MB is rejected and reported as an error."""
    from hermes_seatalk.dispatcher import MAX_INBOUND_RAW_BYTES

    client = FakeClient()
    oversized = b"\xff\xd8\xff" + b"\x00" * (MAX_INBOUND_RAW_BYTES + 1)

    async def _download(_url):
        return oversized, "image/jpeg"

    client.download_media = _download
    client.download_error = None

    fake_adapter = FakeAdapter()
    payload = _dm_payload(event_id="event-1", text="")
    payload["event"]["message"] = {
        "message_id": "msg-1",
        "tag": "image",
        "image": {"content": "https://openapi.seatalk.io/media/huge"},
    }

    await _dispatcher(fake_adapter, client).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.media_urls == [], "oversized media must not be cached"
    errors = event.raw_message["seatalk_media_errors"]
    assert any("250MB" in e or "too large" in e.lower() for e in errors)


# ── File (document) tag ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_t06_18_file_download_success_with_filename():
    """tag=file → bytes cached as document with filename from file_data."""
    client = FakeClient()
    file_bytes = b"hello world text content"

    async def _download(_url):
        return file_bytes, "text/plain"

    client.download_media = _download
    client.download_error = None

    fake_adapter = FakeAdapter()
    payload = _dm_payload(event_id="event-1", text="")
    payload["event"]["message"] = {
        "message_id": "msg-file",
        "tag": "file",
        "file": {
            "content": "https://openapi.seatalk.io/media/file-1",
            "filename": "report.txt",
        },
    }

    await _dispatcher(fake_adapter, client).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.text == "<media:document>"
    assert event.media_urls != [], "document must be cached on success"
    assert "text/plain" in event.media_types
    cached_path = event.media_urls[0]
    assert "report.txt" in cached_path, f"filename should be preserved in path: {cached_path}"


@pytest.mark.asyncio
async def test_t06_19_file_download_failure_shows_placeholder():
    """tag=file download failure → placeholder visible, media_urls empty (MC-EDGE-MEDIA-FAIL-02)."""
    fake_adapter = FakeAdapter()
    payload = _dm_payload(event_id="event-1", text="")
    payload["event"]["message"] = {
        "message_id": "msg-file",
        "tag": "file",
        "file": {
            "content": "https://openapi.seatalk.io/media/file-1",
            "filename": "report.txt",
        },
    }

    # FakeClient.download_media raises by default
    await _dispatcher(fake_adapter).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.text == "<media:document>", "placeholder must be visible even on download failure"
    assert event.media_urls == [], "no cached path when download failed"
    assert any("download failed" in e for e in event.raw_message["seatalk_media_errors"])


@pytest.mark.asyncio
async def test_t06_20_file_extension_inferred_from_content_type():
    """When file has no extension, ext is inferred from Content-Type and appended."""
    client = FakeClient()
    pdf_bytes = b"%PDF-1.4 content here"

    async def _download(_url):
        return pdf_bytes, "application/pdf"

    client.download_media = _download
    client.download_error = None

    fake_adapter = FakeAdapter()
    payload = _dm_payload(event_id="event-1", text="")
    payload["event"]["message"] = {
        "message_id": "msg-pdf",
        "tag": "file",
        "file": {
            # URL has no extension, filename has no extension
            "content": "https://openapi.seatalk.io/media/uuid-abc",
            "filename": "report",
        },
    }

    await _dispatcher(fake_adapter, client).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.media_urls != [], "document must be cached"
    assert event.media_types == ["application/pdf"]
    cached_path = event.media_urls[0]
    assert cached_path.endswith(".pdf") or "report" in cached_path, (
        f"extension should be inferred from content-type: {cached_path}"
    )


@pytest.mark.asyncio
async def test_t06_21_file_fallback_extension_when_no_filename():
    """When file_data has no filename, default 'document' gets inferred extension."""
    client = FakeClient()
    pdf_bytes = b"%PDF-1.4 content here"

    async def _download(_url):
        return pdf_bytes, "application/pdf"

    client.download_media = _download
    client.download_error = None

    fake_adapter = FakeAdapter()
    payload = _dm_payload(event_id="event-1", text="")
    payload["event"]["message"] = {
        "message_id": "msg-pdf",
        "tag": "file",
        "file": {
            "content": "https://openapi.seatalk.io/media/uuid-abc",
            "filename": "",  # empty filename → default 'document'
        },
    }

    await _dispatcher(fake_adapter, client).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.media_urls != []
    cached_path = event.media_urls[0]
    assert ".pdf" in cached_path, (
        f"fallback 'document' should get .pdf extension from content-type: {cached_path}"
    )


# ── Fix 5: default allowlist allows any HTTPS host ────────────────────────────


@pytest.mark.asyncio
async def test_t06_22_cdn_url_allowed_when_allowlist_empty():
    """Default (empty) allowlist allows download from any HTTPS host, e.g. SeaTalk CDN."""
    client = FakeClient()
    pdf_bytes = b"%PDF-1.4 cdn content"

    async def _download(_url):
        return pdf_bytes, "application/pdf"

    client.download_media = _download
    client.download_error = None

    fake_adapter = FakeAdapter()
    payload = _dm_payload(event_id="event-1", text="")
    payload["event"]["message"] = {
        "message_id": "msg-cdn",
        "tag": "file",
        "file": {
            # CDN domain — NOT in the old hard-coded openapi.seatalk.io allowlist
            "content": "https://media-cdn.seatalk.io/files/report.pdf",
            "filename": "report.pdf",
        },
    }

    await _dispatcher(fake_adapter, client).dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.media_urls != [], "CDN URL must be downloadable when allowlist is not configured"
    assert event.raw_message["seatalk_media_errors"] == []


@pytest.mark.asyncio
async def test_t06_23_explicit_allowlist_blocks_unlisted_host():
    """When media_allow_hosts is explicitly set, URLs from other hosts are blocked."""
    fake_adapter = FakeAdapter()
    payload = _dm_payload(event_id="event-1", text="")
    payload["event"]["message"] = {
        "message_id": "msg-blocked",
        "tag": "image",
        "image": {"content": "https://evil.example.com/img.jpg"},
    }

    dispatcher = SeaTalkEventDispatcher(
        adapter=fake_adapter,
        client=FakeClient(),
        app_id="app-id",
        dm_policy="open",
        media_allow_hosts={"openapi.seatalk.io"},
        debounce_idle_seconds=0,
        debounce_max_seconds=0,
    )
    await dispatcher.dispatch(payload, "webhook")

    event = fake_adapter.events[0]
    assert event.media_urls == [], "non-allowlisted host must be blocked when allowlist is configured"
    errors = event.raw_message["seatalk_media_errors"]
    assert any("not allowed" in e for e in errors)
