"""hermes-agent v2026.7.20 compatibility (WBS WC-00 / WC-02).

Covers the gateway connect contract (``is_reconnect``) and the official
``standalone_sender_fn`` outbound hook with its no-runner fallback.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("gateway", reason="requires Hermes gateway")

from hermes_seatalk import adapter as seatalk_adapter  # noqa: E402

pytestmark = pytest.mark.requires_hermes


class FakeSeaTalkClient:
    def __init__(self, name: str):
        self.name = name
        self.calls = []
        self.closed = False

    async def send_single_chat(self, employee_code, message, thread_id=None):
        self.calls.append(("single", employee_code, message, thread_id))
        return {"code": 0, "message_id": f"{self.name}-{len(self.calls)}"}

    async def send_group_chat(self, group_id, message, thread_id=None):
        self.calls.append(("group", group_id, message, thread_id))
        return {"code": 0, "message_id": f"{self.name}-{len(self.calls)}"}

    async def get_employee_code_by_email(self, emails):
        return {email: "EmpFromEmail" for email in emails}

    async def close(self):
        self.closed = True


def _account(app_id: str, **overrides):
    account = {
        "enabled": True,
        "app_id": app_id,
        "app_secret": f"{app_id}-secret",
        "signing_secret": f"{app_id}-signing",
        "mode": "webhook",
        "webhook_host": "127.0.0.1",
        "webhook_port": 8080,
        "webhook_path": "/callback",
    }
    account.update(overrides)
    return account


def _pconfig(clients: dict[str, FakeSeaTalkClient], **extra):
    base = {
        "accounts": {"default": _account("app-default")},
        "clients": clients,
        "outbound_coalescing": False,
    }
    base.update(extra)
    return SimpleNamespace(enabled=True, extra=base)


# --- WC-00: connect contract -------------------------------------------------


@pytest.mark.asyncio
async def test_wc00_connect_accepts_is_reconnect_keyword():
    """gateway/run.py always forwards ``is_reconnect=`` to adapter.connect();
    the adapter must accept it on both the initial and the reconnect path."""
    seatalk = seatalk_adapter.SeaTalkAdapter(SimpleNamespace(enabled=True, extra={}))

    assert await seatalk.connect() is True
    assert await seatalk.connect(is_reconnect=False) is True
    assert await seatalk.connect(is_reconnect=True) is True


# --- WC-02: standalone_sender_fn ---------------------------------------------


def test_wc02_standalone_sender_registered_on_platform_entry():
    captured = {}
    ctx = SimpleNamespace(
        register_platform=lambda **kw: captured.update(kw),
        register_tool=lambda **kw: None,
    )

    seatalk_adapter.register(ctx)

    assert captured.get("standalone_sender_fn") is seatalk_adapter._seatalk_standalone_send


@pytest.mark.asyncio
async def test_wc02_standalone_send_text_and_media(tmp_path):
    client = FakeSeaTalkClient("default")
    image = tmp_path / "photo.png"
    image.write_bytes(b"image")
    document = tmp_path / "report.txt"
    document.write_text("document")

    result = await seatalk_adapter._seatalk_standalone_send(
        _pconfig({"default": client}),
        "group/GroupABC",
        "hello",
        thread_id="ThreadXYZ",
        media_files=[(str(image), False), (str(document), False)],
    )

    assert result["success"] is True
    assert result["message_id"] == "default-3"
    kinds = [(call[0], call[2]["tag"]) for call in client.calls]
    assert kinds == [("group", "text"), ("group", "image"), ("group", "file")]
    assert all(call[1] == "GroupABC" for call in client.calls)
    assert all(call[3] == "ThreadXYZ" for call in client.calls)
    assert client.closed is True


@pytest.mark.asyncio
async def test_wc02_standalone_send_force_document_routes_image_as_file(tmp_path):
    client = FakeSeaTalkClient("default")
    image = tmp_path / "photo.png"
    image.write_bytes(b"image")

    result = await seatalk_adapter._seatalk_standalone_send(
        _pconfig({"default": client}),
        "group/GroupABC",
        "",
        media_files=[(str(image), False)],
        force_document=True,
    )

    assert result["success"] is True
    assert client.calls[0][2]["tag"] == "file"


@pytest.mark.asyncio
async def test_wc02_standalone_send_resolves_email_target():
    """A throwaway adapter has no live connection; email→employee_code
    resolution must still work on the one-shot path."""
    client = FakeSeaTalkClient("default")

    result = await seatalk_adapter._seatalk_standalone_send(
        _pconfig({"default": client}),
        "alice@example.com",
        "hello",
    )

    assert result["success"] is True
    assert client.calls[0][:2] == ("single", "EmpFromEmail")
    assert client.closed is True


@pytest.mark.asyncio
async def test_wc02_standalone_send_without_accounts_errors():
    result = await seatalk_adapter._seatalk_standalone_send(
        SimpleNamespace(enabled=True, extra={}),
        "group/GroupABC",
        "hello",
    )

    assert "error" in result


@pytest.mark.asyncio
async def test_wc02_standalone_send_closes_client_on_failure(tmp_path):
    client = FakeSeaTalkClient("default")

    async def _boom(group_id, message, thread_id=None):
        raise RuntimeError("api down")

    client.send_group_chat = _boom

    result = await seatalk_adapter._seatalk_standalone_send(
        _pconfig({"default": client}),
        "group/GroupABC",
        "hello",
    )

    assert "error" in result
    assert client.closed is True


@pytest.mark.asyncio
async def test_wc02_send_to_platform_falls_back_to_standalone(monkeypatch):
    """No runner/adapter after the lookup retries + pconfig available →
    the send must deliver through the one-shot standalone path instead of
    returning the no-gateway error."""
    import gateway.run as gateway_run

    monkeypatch.setattr(seatalk_adapter, "_RUNNER_LOOKUP_BACKOFF_SECONDS", ())
    monkeypatch.setattr(gateway_run, "_gateway_runner_ref", lambda: None)
    client = FakeSeaTalkClient("default")

    result = await seatalk_adapter._seatalk_send_to_platform(
        "seatalk",
        "group/GroupABC",
        "hello",
        pconfig=_pconfig({"default": client}),
    )

    assert result["success"] is True
    assert client.calls[0][:2] == ("group", "GroupABC")


@pytest.mark.asyncio
async def test_wc02_send_to_platform_without_pconfig_keeps_error(monkeypatch):
    import gateway.run as gateway_run

    monkeypatch.setattr(seatalk_adapter, "_RUNNER_LOOKUP_BACKOFF_SECONDS", ())
    monkeypatch.setattr(gateway_run, "_gateway_runner_ref", lambda: None)

    result = await seatalk_adapter._seatalk_send_to_platform(
        "seatalk",
        "group/GroupABC",
        "hello",
    )

    assert "error" in result
