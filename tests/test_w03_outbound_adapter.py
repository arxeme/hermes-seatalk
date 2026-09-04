from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from hermes_seatalk import adapter
from hermes_seatalk.client import SeaTalkProtocolError
from hermes_seatalk.targets import parse_seatalk_target


class FakeSeaTalkClient:
    def __init__(self):
        self.calls = []
        self.email_map = {}

    async def send_single_chat(self, employee_code, message, thread_id=None):
        self.calls.append(("single", employee_code, message, thread_id))
        return {"code": 0, "message_id": f"m-{len(self.calls)}"}

    async def send_group_chat(self, group_id, message, thread_id=None):
        self.calls.append(("group", group_id, message, thread_id))
        return {"code": 0, "message_id": f"m-{len(self.calls)}"}

    async def send_single_chat_typing(self, employee_code, thread_id=None):
        self.calls.append(("typing-single", employee_code, None, thread_id))

    async def send_group_chat_typing(self, group_id, thread_id=None):
        self.calls.append(("typing-group", group_id, None, thread_id))

    async def get_employee_code_by_email(self, emails):
        return {email: self.email_map.get(email) for email in emails}

    def remember_employee_email(self, email, employee_code):
        self.email_map[email.strip().lower()] = employee_code.strip()

    async def download_media(self, _url):
        return b"image-bytes", "image/png"

    async def close(self):
        return None


class FailingClient(FakeSeaTalkClient):
    async def send_single_chat(self, employee_code, message, thread_id=None):
        raise SeaTalkProtocolError("boom")


def _config(client, **extra):
    account_coalescing = extra.pop("outbound_coalescing", None)
    account = {
        "app_id": "app-id",
        "app_secret": "app-secret",
        "signing_secret": "signing-secret",
        "mode": "webhook",
    }
    if account_coalescing is not None:
        account["outbound_coalescing"] = account_coalescing
    base = {
        "accounts": {"default": account},
        "clients": {"default": client},
    }
    base.update(extra)
    return SimpleNamespace(extra=base, enabled=True)


@pytest.mark.asyncio
async def test_t03_01_home_channel_send(monkeypatch):
    monkeypatch.setenv("SEATALK_HOME_CHANNEL", "EmpHome")
    client = FakeSeaTalkClient()
    seatalk = adapter.SeaTalkAdapter(_config(
        client,
        outbound_coalescing=False,
    ))

    result = await seatalk.send("seatalk", "hello")

    assert result.success is True
    assert client.calls == [("single", "EmpHome", {
        "tag": "text",
        "text": {"format": 1, "content": "hello"},
    }, None)]


@pytest.mark.asyncio
async def test_t03_02_specified_channel_send(monkeypatch):
    client = FakeSeaTalkClient()
    seatalk = adapter.SeaTalkAdapter(_config(client, outbound_coalescing=False))

    await seatalk.send("group/GroupABC", "hello group")

    assert client.calls[0] == ("group", "GroupABC", {
        "tag": "text",
        "text": {"format": 1, "content": "hello group"},
    }, None)


@pytest.mark.asyncio
async def test_t03_03_specified_thread_send(monkeypatch):
    client = FakeSeaTalkClient()
    seatalk = adapter.SeaTalkAdapter(_config(client, outbound_coalescing=False))

    await seatalk.send("EmpABC", "threaded", metadata={"thread_id": "ThreadXYZ"})

    assert client.calls[0][3] == "ThreadXYZ"


@pytest.mark.asyncio
@pytest.mark.requires_hermes
async def test_t03_04_long_text_is_split_in_order(monkeypatch):
    if not adapter._HAS_HERMES_BASE:
        pytest.skip("requires Hermes BasePlatformAdapter truncate behavior")
    client = FakeSeaTalkClient()
    seatalk = adapter.SeaTalkAdapter(_config(client, outbound_coalescing=False))

    await seatalk.send("EmpABC", "a" * 4100)

    assert len(client.calls) == 2
    assert client.calls[0][2]["text"]["content"].startswith("a")
    assert client.calls[0][2]["text"]["content"].endswith("(1/2)")
    assert client.calls[1][2]["text"]["content"].endswith("(2/2)")


@pytest.mark.asyncio
async def test_t03_05_image_and_file_payloads(monkeypatch, tmp_path: Path):
    client = FakeSeaTalkClient()
    seatalk = adapter.SeaTalkAdapter(_config(client))
    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"image-bytes")
    file_path = tmp_path / "report.bin"
    file_path.write_bytes(b"file-bytes")

    image_result = await seatalk.send_image_file("EmpABC", str(image_path))
    file_result = await seatalk.send_document("group/GroupABC", str(file_path), file_name=None)

    assert image_result.success is True
    assert file_result.success is True
    assert client.calls[0] == ("single", "EmpABC", {
        "tag": "image",
        "image": {"content": "aW1hZ2UtYnl0ZXM="},
    }, None)
    assert client.calls[1] == ("group", "GroupABC", {
        "tag": "file",
        "file": {"content": "ZmlsZS1ieXRlcw==", "filename": "report.bin"},
    }, None)


@pytest.mark.asyncio
async def test_t03_06_send_failure_propagates(monkeypatch):
    seatalk = adapter.SeaTalkAdapter(_config(FailingClient(), outbound_coalescing=False))

    result = await seatalk.send("EmpABC", "hello")

    assert result.success is False
    assert "boom" in result.error
    assert result.retryable is True


@pytest.mark.asyncio
async def test_t03_07_coalescer_default_merges_same_target(monkeypatch):
    client = FakeSeaTalkClient()
    seatalk = adapter.SeaTalkAdapter(_config(
        client,
        outbound_coalescing_idle_seconds=60,
    ))

    await seatalk.send("EmpABC", "one")
    await seatalk.send("EmpABC", "two")
    assert client.calls == []

    await seatalk.flush_outbound()

    assert client.calls == [("single", "EmpABC", {
        "tag": "text",
        "text": {"format": 1, "content": "one\n\ntwo"},
    }, None)]


@pytest.mark.asyncio
@pytest.mark.requires_hermes
async def test_t03_12_long_text_bypasses_coalescer(monkeypatch):
    if not adapter._HAS_HERMES_BASE:
        pytest.skip("requires Hermes BasePlatformAdapter truncate behavior")
    client = FakeSeaTalkClient()
    seatalk = adapter.SeaTalkAdapter(_config(
        client,
        outbound_coalescing_idle_seconds=60,
    ))

    result = await seatalk.send("EmpABC", "a" * 4100)

    assert result.success is True
    assert len(client.calls) == 2
    assert client.calls[0][2]["text"]["content"].endswith("(1/2)")
    assert client.calls[1][2]["text"]["content"].endswith("(2/2)")


@pytest.mark.asyncio
@pytest.mark.requires_hermes
async def test_t03_13_long_text_failure_propagates_with_coalescing_enabled(monkeypatch):
    if not adapter._HAS_HERMES_BASE:
        pytest.skip("requires Hermes BasePlatformAdapter truncate behavior")
    seatalk = adapter.SeaTalkAdapter(_config(
        FailingClient(),
        outbound_coalescing_idle_seconds=60,
    ))

    result = await seatalk.send("EmpABC", "a" * 4100)

    assert result.success is False
    assert "boom" in result.error


@pytest.mark.asyncio
async def test_t03_08_coalescer_isolates_threads_and_can_disable(monkeypatch):
    client = FakeSeaTalkClient()
    seatalk = adapter.SeaTalkAdapter(_config(
        client,
        outbound_coalescing_idle_seconds=60,
    ))

    await seatalk.send("EmpABC", "one", metadata={"thread_id": "A"})
    await seatalk.send("EmpABC", "two", metadata={"thread_id": "B"})
    await seatalk.flush_outbound()

    assert [call[3] for call in client.calls] == ["A", "B"]

    direct_client = FakeSeaTalkClient()
    direct = adapter.SeaTalkAdapter(_config(direct_client, outbound_coalescing=False))
    await direct.send("EmpABC", "one")
    await direct.send("EmpABC", "two")
    assert [call[2]["text"]["content"] for call in direct_client.calls] == ["one", "two"]


@pytest.mark.asyncio
async def test_t03_09_shutdown_flushes_and_media_bypasses_coalescer(monkeypatch, tmp_path: Path):
    client = FakeSeaTalkClient()
    seatalk = adapter.SeaTalkAdapter(_config(
        client,
        outbound_coalescing_idle_seconds=60,
    ))
    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"image-bytes")

    await seatalk.send("EmpABC", "queued")
    await seatalk.send_image_file("EmpABC", str(image_path))
    assert client.calls[0][2]["tag"] == "image"

    await seatalk.disconnect()

    assert client.calls[1][2]["text"]["content"] == "queued"


@pytest.mark.asyncio
async def test_t03_10_processing_indicator_off_skips_typing(monkeypatch):
    client = FakeSeaTalkClient()
    seatalk = adapter.SeaTalkAdapter(_config(client, processing_indicator="off"))

    result = await seatalk.send_typing("EmpABC")

    assert result.success is True
    assert client.calls == []


@pytest.mark.asyncio
async def test_t03_11_per_account_coalescing_isolation(monkeypatch):
    default_client = FakeSeaTalkClient()
    staging_client = FakeSeaTalkClient()
    cfg = SimpleNamespace(extra={
        "accounts": {
            "default": {
                "app_id": "app-id-1",
                "app_secret": "secret-1",
                "signing_secret": "signing-1",
                "mode": "webhook",
                "outbound_coalescing": True,
            },
            "staging": {
                "app_id": "app-id-2",
                "app_secret": "secret-2",
                "signing_secret": "signing-2",
                "mode": "webhook",
                "outbound_coalescing": False,
            },
        },
        "clients": {"default": default_client, "staging": staging_client},
        "outbound_coalescing_idle_seconds": 60,
    }, enabled=True)
    seatalk = adapter.SeaTalkAdapter(cfg)

    await seatalk.send("default:EmpABC", "queued")
    await seatalk.send("staging:EmpXYZ", "immediate")

    assert staging_client.calls == [("single", "EmpXYZ", {
        "tag": "text",
        "text": {"format": 1, "content": "immediate"},
    }, None)]
    assert default_client.calls == []

    await seatalk.flush_outbound()

    assert default_client.calls == [("single", "EmpABC", {
        "tag": "text",
        "text": {"format": 1, "content": "queued"},
    }, None)]


@pytest.mark.asyncio
async def test_t03_14_inbound_event_caches_email_for_later_send(monkeypatch):
    client = FakeSeaTalkClient()
    seatalk = adapter.SeaTalkAdapter(_config(
        client,
        outbound_coalescing=False,
    ))

    await seatalk._dispatch_runtime_event("default", {
        "event_id": "event-1",
        "event_type": "message_from_bot_subscriber",
        "app_id": "app-id",
        "event": {
            "employee_code": "EmpABC",
            "email": "Alice@Example.com",
            "message": {
                "message_id": "msg-1",
                "tag": "text",
                "text": {"plain_text": "hello"},
            },
        },
    }, "relay")
    result = await seatalk.send("alice@example.com", "reply")

    assert result.success is True
    assert client.calls[-1] == ("single", "EmpABC", {
        "tag": "text",
        "text": {"format": 1, "content": "reply"},
    }, None)


def test_t08_target_parser_full_formats():
    assert parse_seatalk_target("EmpABC").chat_id == "EmpABC"
    assert parse_seatalk_target("Alice@Example.com").chat_id == "alice@example.com"
    assert parse_seatalk_target("group/GroupABC").chat_id == "group/GroupABC"
    assert parse_seatalk_target("alice@example.com:ThreadXYZ").thread_id == "ThreadXYZ"
    assert parse_seatalk_target("EmpABC:ThreadXYZ").thread_id == "ThreadXYZ"
    target = parse_seatalk_target("group/GroupABC:ThreadXYZ")
    assert (target.chat_id, target.thread_id, target.is_group) == (
        "group/GroupABC",
        "ThreadXYZ",
        True,
    )
