"""Tests for hermes_seatalk.tools - SeaTalk query tool handler."""

from __future__ import annotations

import json

import pytest

from hermes_seatalk.tools import (
    SEATALK_TOOL_SCHEMA,
    _resolve_quoted_messages,
    make_seatalk_tool_handler,
    register_seatalk_tool,
)


# ── Fake client ───────────────────────────────────────────────────────────────

class FakeSeaTalkClient:
    def __init__(self, **responses):
        self.responses = responses
        self.calls: list[tuple] = []

    async def get_group_chat_history(self, group_id, *, page_size=50, cursor=None):
        self.calls.append(("get_group_chat_history", group_id, page_size, cursor))
        return self.responses.get("group_history", {"group_chat_messages": [], "next_cursor": ""})

    async def get_group_info(self, group_id):
        self.calls.append(("get_group_info", group_id))
        return self.responses.get("group_info", {"group_id": group_id, "group_name": "Test"})

    async def get_joined_group_chats(self, *, page_size=None, cursor=None):
        self.calls.append(("get_joined_group_chats", page_size, cursor))
        return self.responses.get("group_list", {"groups": []})

    async def get_group_thread(self, group_id, thread_id, *, page_size=None, cursor=None):
        self.calls.append(("get_group_thread", group_id, thread_id, page_size, cursor))
        return self.responses.get("group_thread", {"thread_messages": []})

    async def get_dm_thread(self, employee_code, thread_id, *, page_size=None, cursor=None):
        self.calls.append(("get_dm_thread", employee_code, thread_id, page_size, cursor))
        return self.responses.get("dm_thread", {"thread_messages": []})

    async def get_message_by_id(self, message_id):
        self.calls.append(("get_message_by_id", message_id))
        return self.responses.get("message", {"message_id": message_id, "text": "Hello"})


def _make_handler(client=None):
    get_client = (lambda account_id=None: client) if client is not None else (lambda account_id=None: None)
    return make_seatalk_tool_handler(get_client=get_client)


# ── Schema ────────────────────────────────────────────────────────────────────

def test_t11_01_schema_name_and_required():
    assert SEATALK_TOOL_SCHEMA["name"] == "seatalk_query"
    assert "description" in SEATALK_TOOL_SCHEMA
    params = SEATALK_TOOL_SCHEMA["parameters"]
    assert params["type"] == "object"
    assert params["required"] == ["action"]


def test_t11_02_schema_action_enum():
    actions = set(SEATALK_TOOL_SCHEMA["parameters"]["properties"]["action"]["enum"])
    assert actions == {"group_history", "group_info", "group_list", "thread_history", "get_message"}


def test_t11_03_schema_has_all_parameter_fields():
    props = SEATALK_TOOL_SCHEMA["parameters"]["properties"]
    for field in ("group_id", "thread_id", "employee_code", "message_id", "page_size", "cursor", "account_id"):
        assert field in props, f"Missing field: {field}"


# ── group_history ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t11_10_group_history_reverses_messages():
    msgs = [{"id": "1", "text": "newest"}, {"id": "2", "text": "older"}]
    client = FakeSeaTalkClient(group_history={"group_chat_messages": msgs})
    handler = _make_handler(client)

    result = json.loads(await handler({"action": "group_history", "group_id": "G123"}))

    assert result["group_chat_messages"][0]["id"] == "2"
    assert result["group_chat_messages"][1]["id"] == "1"


@pytest.mark.asyncio
async def test_t11_11_group_history_resolves_quoted_messages():
    msgs = [{"id": "m1", "quoted_message_id": "q1"}]
    client = FakeSeaTalkClient(
        group_history={"group_chat_messages": msgs},
        message={"message_id": "q1", "text": "quoted text"},
    )
    handler = _make_handler(client)

    result = json.loads(await handler({"action": "group_history", "group_id": "G1"}))

    assert result["group_chat_messages"][0]["quoted_message"]["message_id"] == "q1"


@pytest.mark.asyncio
async def test_t11_12_group_history_passes_page_size_and_cursor():
    client = FakeSeaTalkClient(group_history={"group_chat_messages": []})
    handler = _make_handler(client)

    await handler({"action": "group_history", "group_id": "G1", "page_size": 10, "cursor": "abc"})

    assert client.calls[0] == ("get_group_chat_history", "G1", 10, "abc")


@pytest.mark.asyncio
async def test_t11_13_group_history_default_page_size():
    client = FakeSeaTalkClient(group_history={"group_chat_messages": []})
    handler = _make_handler(client)

    await handler({"action": "group_history", "group_id": "G1"})

    _, _, page_size, cursor = client.calls[0]
    assert page_size == 50
    assert cursor is None


# ── group_info ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t11_20_group_info_returns_details():
    client = FakeSeaTalkClient(group_info={"group_id": "G1", "group_name": "Team", "members": []})
    handler = _make_handler(client)

    result = json.loads(await handler({"action": "group_info", "group_id": "G1"}))

    assert result["group_name"] == "Team"
    assert client.calls == [("get_group_info", "G1")]


# ── group_list ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t11_30_group_list_returns_joined_groups():
    groups = [{"group_id": "G1"}, {"group_id": "G2"}]
    client = FakeSeaTalkClient(group_list={"groups": groups})
    handler = _make_handler(client)

    result = json.loads(await handler({"action": "group_list"}))

    assert len(result["groups"]) == 2
    assert client.calls[0] == ("get_joined_group_chats", None, None)


@pytest.mark.asyncio
async def test_t11_31_group_list_passes_page_size_and_cursor():
    client = FakeSeaTalkClient(group_list={"groups": []})
    handler = _make_handler(client)

    await handler({"action": "group_list", "page_size": 20, "cursor": "c2"})

    assert client.calls[0] == ("get_joined_group_chats", 20, "c2")


# ── thread_history ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t11_40_group_thread_reverses_messages():
    msgs = [{"id": "t1", "text": "newest"}, {"id": "t2", "text": "older"}]
    client = FakeSeaTalkClient(group_thread={"thread_messages": msgs})
    handler = _make_handler(client)

    result = json.loads(await handler({
        "action": "thread_history",
        "thread_id": "T1",
        "group_id": "G1",
    }))

    assert result["thread_messages"][0]["id"] == "t2"
    assert result["thread_messages"][1]["id"] == "t1"


@pytest.mark.asyncio
async def test_t11_41_dm_thread_requires_employee_code():
    client = FakeSeaTalkClient()
    handler = _make_handler(client)

    result = json.loads(await handler({"action": "thread_history", "thread_id": "T1"}))

    assert "error" in result
    assert "employee_code" in result["error"]


@pytest.mark.asyncio
async def test_t11_42_dm_thread_with_employee_code():
    msgs = [{"id": "d1"}, {"id": "d2"}]
    client = FakeSeaTalkClient(dm_thread={"thread_messages": msgs})
    handler = _make_handler(client)

    result = json.loads(await handler({
        "action": "thread_history",
        "thread_id": "T1",
        "employee_code": "emp123",
    }))

    assert result["thread_messages"][0]["id"] == "d2"
    assert client.calls[0] == ("get_dm_thread", "emp123", "T1", None, None)


@pytest.mark.asyncio
async def test_t11_43_thread_history_resolves_quoted_messages():
    msgs = [{"id": "m1", "quoted_message_id": "q1"}]
    client = FakeSeaTalkClient(
        group_thread={"thread_messages": msgs},
        message={"message_id": "q1", "text": "original"},
    )
    handler = _make_handler(client)

    result = json.loads(await handler({
        "action": "thread_history",
        "thread_id": "T1",
        "group_id": "G1",
    }))

    assert result["thread_messages"][0]["quoted_message"]["message_id"] == "q1"


@pytest.mark.asyncio
async def test_t11_44_thread_history_passes_pagination():
    client = FakeSeaTalkClient(group_thread={"thread_messages": []})
    handler = _make_handler(client)

    await handler({
        "action": "thread_history",
        "thread_id": "T1",
        "group_id": "G1",
        "page_size": 25,
        "cursor": "tok",
    })

    assert client.calls[0] == ("get_group_thread", "G1", "T1", 25, "tok")


# ── get_message ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t11_50_get_message_by_id():
    client = FakeSeaTalkClient(message={"message_id": "M1", "text": "Hello"})
    handler = _make_handler(client)

    result = json.loads(await handler({"action": "get_message", "message_id": "M1"}))

    assert result["message_id"] == "M1"
    assert client.calls == [("get_message_by_id", "M1")]


# ── _resolve_quoted_messages ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t11_55_resolve_skips_messages_without_quoted_id():
    client = FakeSeaTalkClient(message={"message_id": "q1"})
    msgs = [{"id": "m1"}, {"id": "m2", "quoted_message_id": ""}]

    await _resolve_quoted_messages(client, msgs)

    assert client.calls == []
    assert "quoted_message" not in msgs[0]


@pytest.mark.asyncio
async def test_t11_56_resolve_sets_none_on_fetch_failure():
    class FailClient:
        async def get_message_by_id(self, _message_id):
            raise RuntimeError("not found")

    msgs = [{"id": "m1", "quoted_message_id": "q1"}]
    await _resolve_quoted_messages(FailClient(), msgs)

    assert msgs[0]["quoted_message"] is None


# ── Error handling ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t11_60_client_not_available_returns_error():
    handler = make_seatalk_tool_handler(get_client=lambda account_id=None: None)

    result = json.loads(await handler({"action": "group_info", "group_id": "G1"}))

    assert "error" in result


@pytest.mark.asyncio
async def test_t11_61_unknown_action_returns_error():
    client = FakeSeaTalkClient()
    handler = _make_handler(client)

    result = json.loads(await handler({"action": "unknown_action"}))

    assert "error" in result
    assert "unknown_action" in result["error"]


@pytest.mark.asyncio
async def test_t11_62_api_exception_returns_error():
    class FailingClient:
        async def get_group_info(self, _group_id):
            raise RuntimeError("SeaTalk API unavailable")

    handler = _make_handler(FailingClient())

    result = json.loads(await handler({"action": "group_info", "group_id": "G1"}))

    assert "error" in result
    assert "SeaTalk API unavailable" in result["error"]


@pytest.mark.asyncio
async def test_t11_63_handler_returns_json_string():
    client = FakeSeaTalkClient(group_info={"group_id": "G1", "group_name": "Team"})
    handler = _make_handler(client)

    raw = await handler({"action": "group_info", "group_id": "G1"})

    assert isinstance(raw, str)
    json.loads(raw)  # must be valid JSON


# ── register_seatalk_tool ─────────────────────────────────────────────────────

def test_t11_70_register_uses_ctx():
    class FakeCtx:
        def __init__(self):
            self.tools: list[dict] = []
        def register_tool(self, **kwargs):
            self.tools.append(kwargs)

    ctx = FakeCtx()
    register_seatalk_tool(ctx)

    assert len(ctx.tools) == 1
    tool = ctx.tools[0]
    assert tool["name"] == "seatalk_query"
    assert tool["toolset"] == "seatalk-platform"
    assert tool["is_async"] is True
    assert callable(tool["handler"])


def test_t11_71_register_skips_without_register_tool():
    class MinimalCtx:
        pass

    register_seatalk_tool(MinimalCtx())  # must not raise


# ── account_id support ────────────────────────────────────────────────────────

def test_t11_72_schema_account_id_not_required():
    required = SEATALK_TOOL_SCHEMA["parameters"]["required"]
    assert "account_id" not in required
    props = SEATALK_TOOL_SCHEMA["parameters"]["properties"]
    assert props["account_id"]["type"] == "string"


@pytest.mark.asyncio
async def test_t11_73_account_id_passed_to_get_client():
    received: list[str | None] = []

    def capturing_get_client(account_id=None):
        received.append(account_id)
        return FakeSeaTalkClient(group_info={"group_id": "G1"})

    handler = make_seatalk_tool_handler(get_client=capturing_get_client)
    await handler({"action": "group_info", "group_id": "G1", "account_id": "staging"})

    assert received == ["staging"]


@pytest.mark.asyncio
async def test_t11_74_no_account_id_passes_none_to_get_client():
    received: list[str | None] = []

    def capturing_get_client(account_id=None):
        received.append(account_id)
        return FakeSeaTalkClient(group_info={"group_id": "G1"})

    handler = make_seatalk_tool_handler(get_client=capturing_get_client)
    await handler({"action": "group_info", "group_id": "G1"})

    assert received == [None]


@pytest.mark.asyncio
async def test_t11_75_unknown_account_id_returns_error():
    def no_client(account_id=None):
        return None  # unknown account → client not found

    handler = make_seatalk_tool_handler(get_client=no_client)
    result = json.loads(await handler({"action": "group_info", "group_id": "G1", "account_id": "unknown"}))

    assert "error" in result
