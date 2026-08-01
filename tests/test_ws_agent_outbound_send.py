"""WBS WS-00..WS-03: the seatalk tool's send_message action.

Covers the whitelist guard (the reason arbitrary targets are safe), email
resolution, media routing, and the per-account action switch.
"""
from __future__ import annotations

import json

import pytest

from hermes_seatalk.adapter import SeaTalkAccountConfig, _build_account_config
from hermes_seatalk.tools import make_seatalk_tool_handler

pytestmark = pytest.mark.asyncio


class FakeSendClient:
    def __init__(self, emails: dict[str, str] | None = None):
        self.emails = emails or {}
        self.single: list[tuple] = []
        self.group: list[tuple] = []

    async def get_employee_code_by_email(self, emails):
        return {e: self.emails.get(e) for e in emails}

    async def send_single_chat(self, employee_code, message, thread_id=None):
        self.single.append((employee_code, message, thread_id))
        return {"message_id": f"dm-{len(self.single)}"}

    async def send_group_chat(self, group_id, message, thread_id=None):
        self.group.append((group_id, message, thread_id))
        return {"message_id": f"grp-{len(self.group)}"}


def _account(**overrides) -> SeaTalkAccountConfig:
    data = {
        "app_id": "app", "app_secret": "sec", "signing_secret": "sig",
        "mode": "websocket", "dm_policy": "allowlist",
        "allow_from": ["alice@example.com"],
        "group_policy": "open", "group_allow_from": ["G1"],
    }
    data.update(overrides)
    return _build_account_config("default", data)


def _handler(client, account):
    return make_seatalk_tool_handler(
        get_client=lambda account_id=None: client,
        get_account=lambda account_id=None: account,
    )


async def _send(client, account, **args):
    handler = _handler(client, account)
    return json.loads(await handler({"action": "send_message", **args}))


# ── whitelist guard ──────────────────────────────────────────────────────────

async def test_dm_target_in_allow_from_is_sent():
    client = FakeSendClient()
    out = await _send(client, _account(allow_from=["EmpA"]), target="EmpA", text="hi")

    assert out["sent"] == [{"type": "text", "message_id": "dm-1"}]
    assert client.single[0][0] == "EmpA"


async def test_dm_target_outside_allow_from_is_refused_without_api_call():
    client = FakeSendClient()
    out = await _send(client, _account(allow_from=["EmpA"]), target="EmpB", text="hi")

    assert "not in allow_from" in out["error"]
    assert client.single == [] and client.group == []


async def test_empty_allow_from_fails_closed():
    client = FakeSendClient()
    out = await _send(client, _account(allow_from=[]), target="EmpA", text="hi")

    assert "not in allow_from" in out["error"]
    assert client.single == []


async def test_wildcard_allow_from_permits_any_target():
    client = FakeSendClient()
    out = await _send(client, _account(allow_from=["*"]), target="Whoever", text="hi")

    assert out["sent"][0]["message_id"] == "dm-1"


async def test_missing_account_config_refuses_to_send():
    client = FakeSendClient()
    out = await _send(client, None, target="EmpA", text="hi")

    assert "whitelist" in out["error"]
    assert client.single == []


# ── email resolution ─────────────────────────────────────────────────────────

async def test_email_resolves_to_employee_code_and_matches_whitelist_by_email():
    """allow_from holds the email; the send goes to the resolved employee code."""
    client = FakeSendClient(emails={"alice@example.com": "EmpAlice"})
    out = await _send(client, _account(allow_from=["alice@example.com"]),
                      target="alice@example.com", text="hi")

    assert out["target"]["chat_id"] == "EmpAlice"
    assert client.single[0][0] == "EmpAlice"


async def test_email_target_matches_whitelist_by_resolved_code():
    """allow_from may hold the employee code instead of the email."""
    client = FakeSendClient(emails={"alice@example.com": "EmpAlice"})
    out = await _send(client, _account(allow_from=["EmpAlice"]),
                      target="alice@example.com", text="hi")

    assert out["sent"][0]["message_id"] == "dm-1"


async def test_unresolvable_email_errors_before_sending():
    client = FakeSendClient(emails={})
    out = await _send(client, _account(allow_from=["*"]),
                      target="ghost@example.com", text="hi")

    assert "no active SeaTalk employee" in out["error"]
    assert client.single == []


# ── groups ───────────────────────────────────────────────────────────────────

async def test_group_target_in_group_allow_from_is_sent():
    client = FakeSendClient()
    out = await _send(client, _account(group_allow_from=["G1"]), target="group/G1", text="hi")

    assert client.group[0][0] == "G1"
    assert out["target"]["is_group"] is True


async def test_group_target_outside_group_allow_from_is_refused():
    client = FakeSendClient()
    out = await _send(client, _account(group_allow_from=["G1"]), target="group/G9", text="hi")

    assert "not in group_allow_from" in out["error"]
    assert client.group == []


async def test_group_policy_disabled_refuses_even_if_listed():
    client = FakeSendClient()
    out = await _send(client, _account(group_policy="disabled", group_allow_from=["G1"]),
                      target="group/G1", text="hi")

    assert "group_policy=disabled" in out["error"]
    assert client.group == []


async def test_thread_id_suffix_is_forwarded():
    client = FakeSendClient()
    await _send(client, _account(group_allow_from=["G1"]), target="group/G1:T7", text="hi")

    assert client.group[0][2] == "T7"


# ── media ────────────────────────────────────────────────────────────────────

async def test_image_and_document_media_route_by_extension(tmp_path):
    img = tmp_path / "p.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x")
    doc = tmp_path / "r.txt"
    doc.write_text("hello")
    client = FakeSendClient()

    out = await _send(client, _account(allow_from=["*"]), target="EmpA",
                      media_paths=[str(img), str(doc)])

    assert [s["type"] for s in out["sent"]] == ["image", "file"]
    assert [m["tag"] for _, m, _ in client.single] == ["image", "file"]


async def test_missing_media_path_errors_and_reports_what_was_sent(tmp_path):
    client = FakeSendClient()
    out = await _send(client, _account(allow_from=["*"]), target="EmpA",
                      text="hi", media_paths=[str(tmp_path / "nope.png")])

    assert "media path does not exist" in out["error"]
    # the text went out before the bad attachment; say so rather than implying nothing did
    assert out["sent"] == [{"type": "text", "message_id": "dm-1"}]


async def test_text_and_media_both_absent_is_rejected():
    client = FakeSendClient()
    out = await _send(client, _account(allow_from=["*"]), target="EmpA")

    assert "provide text and/or media_paths" in out["error"]
    assert client.single == []


async def test_missing_target_is_rejected():
    client = FakeSendClient()
    out = await _send(client, _account(allow_from=["*"]), text="hi")

    assert "target is required" in out["error"]


# ── per-account action switch (WS-00) ────────────────────────────────────────

async def test_send_disabled_per_account():
    client = FakeSendClient()
    out = await _send(client, _account(tools={"send_message": False}),
                      target="EmpA", text="hi")

    assert out["error"] == "action 'send_message' is disabled"
    assert client.single == []


async def test_disabling_send_leaves_read_actions_working():
    account = _account(tools={"send_message": False})
    handler = make_seatalk_tool_handler(
        get_client=lambda account_id=None: FakeReadClient(),
        get_account=lambda account_id=None: account,
    )
    out = json.loads(await handler({"action": "group_info", "group_id": "G1"}))

    assert out["group_id"] == "G1"


async def test_tools_absent_means_all_actions_enabled():
    client = FakeSendClient()
    account = _account(allow_from=["EmpA"])
    assert account.tools == {}

    out = await _send(client, account, target="EmpA", text="hi")

    assert "error" not in out
    assert out["sent"][0]["message_id"] == "dm-1"


class FakeReadClient:
    async def get_group_info(self, group_id):
        return {"group_id": group_id}
