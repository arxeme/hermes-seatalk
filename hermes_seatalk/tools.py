"""SeaTalk query tool for Hermes Agent."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

SEATALK_TOOL_SCHEMA: dict[str, Any] = {
    "name": "seatalk",
    "description": (
        "SeaTalk operations. Actions: group_history (group chat messages, chronological order), "
        "group_info (group details), group_list (joined groups), "
        "thread_history (thread messages, chronological order), "
        "get_message (retrieve a single message by ID). "
        "History and thread results include resolved quoted_message for messages that quote another message."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["group_history", "group_info", "group_list", "thread_history", "get_message"],
                "description": (
                    "group_history: Get group chat message history (requires 'Get Chat History' app permission). "
                    "Messages are returned in chronological order (oldest to newest). "
                    "The first page (no cursor) contains the most recent messages. "
                    "Use next_cursor from the response to fetch older pages. "
                    "group_info: Get group chat details. "
                    "group_list: List groups the bot has joined. "
                    "thread_history: Get thread messages in chronological order (oldest to newest). "
                    "The first page (no cursor) contains the most recent replies. "
                    "Use next_cursor to fetch older replies. "
                    "get_message: Get a message by its ID. Can resolve any message_id or quoted_message_id."
                ),
            },
            "group_id": {
                "type": "string",
                "description": (
                    "Group chat ID. Required for: group_history, group_info. "
                    "Optional for thread_history (provide for group thread, omit for DM thread)."
                ),
            },
            "thread_id": {
                "type": "string",
                "description": "Thread ID. Required for: thread_history.",
            },
            "employee_code": {
                "type": "string",
                "description": "Employee code. Required for thread_history when group_id is omitted (DM thread).",
            },
            "message_id": {
                "type": "string",
                "description": "Message ID to retrieve. Required for: get_message.",
            },
            "page_size": {
                "type": "integer",
                "description": "Page size (1-100, default 50). Applies to: group_history, group_list, thread_history.",
                "minimum": 1,
                "maximum": 100,
            },
            "cursor": {
                "type": "string",
                "description": (
                    "Pagination cursor. Omit for the first request to get the latest messages. "
                    "To fetch older messages, pass the next_cursor value from the previous response."
                ),
            },
            "account_id": {
                "type": "string",
                "description": (
                    "SeaTalk account ID to use when multiple accounts are configured. "
                    "Omit to use the default account."
                ),
            },
        },
        "required": ["action"],
    },
}


async def _resolve_quoted_messages(client: Any, messages: list[dict[str, Any]]) -> None:
    """Resolve quoted_message_id fields to full message objects, in-place."""
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        qid = msg.get("quoted_message_id")
        if not qid or not isinstance(qid, str):
            continue
        try:
            msg["quoted_message"] = await client.get_message_by_id(qid)
        except Exception:  # noqa: BLE001
            msg["quoted_message"] = None


def _get_seatalk_tool_client(account_id: str | None = None) -> Any | None:
    """Get a SeaTalk client from the running gateway adapter."""
    try:
        from gateway.run import _gateway_runner_ref
    except ImportError:
        return None

    runner = _gateway_runner_ref()
    if not runner:
        return None

    try:
        from hermes_seatalk.adapter import SeaTalkAdapter
    except ImportError:
        return None

    for adapter_instance in runner.adapters.values():
        if isinstance(adapter_instance, SeaTalkAdapter):
            key = account_id if account_id else adapter_instance._default_account_id
            runtime = adapter_instance._runtimes.get(key)
            if runtime:
                return runtime.client
    return None


def make_seatalk_tool_handler(get_client: Any = None) -> Any:
    """Create the seatalk tool handler with an injectable client getter."""
    _get_client = get_client if get_client is not None else _get_seatalk_tool_client

    async def handler(args: dict[str, Any], **_kwargs: Any) -> str:
        action = args.get("action", "")
        account_id = args.get("account_id")
        client = _get_client(account_id=account_id)
        if client is None:
            return json.dumps({
                "error": "SeaTalk client not available. Is the gateway running with SeaTalk connected?"
            })

        try:
            if action == "group_history":
                data = await client.get_group_chat_history(
                    args["group_id"],
                    page_size=args.get("page_size", 50),
                    cursor=args.get("cursor"),
                )
                msgs = data.get("group_chat_messages")
                if isinstance(msgs, list):
                    msgs.reverse()
                    data["group_chat_messages"] = msgs
                    await _resolve_quoted_messages(client, msgs)
                return json.dumps(data)

            if action == "group_info":
                return json.dumps(await client.get_group_info(args["group_id"]))

            if action == "group_list":
                return json.dumps(await client.get_joined_group_chats(
                    page_size=args.get("page_size"),
                    cursor=args.get("cursor"),
                ))

            if action == "thread_history":
                thread_id = args.get("thread_id", "")
                group_id = args.get("group_id")
                if group_id:
                    data = await client.get_group_thread(
                        group_id, thread_id,
                        page_size=args.get("page_size"),
                        cursor=args.get("cursor"),
                    )
                else:
                    employee_code = args.get("employee_code")
                    if not employee_code:
                        return json.dumps({
                            "error": "employee_code is required for DM thread (when group_id is omitted)"
                        })
                    data = await client.get_dm_thread(
                        employee_code, thread_id,
                        page_size=args.get("page_size"),
                        cursor=args.get("cursor"),
                    )
                msgs = data.get("thread_messages")
                if isinstance(msgs, list):
                    msgs.reverse()
                    data["thread_messages"] = msgs
                    await _resolve_quoted_messages(client, msgs)
                return json.dumps(data)

            if action == "get_message":
                return json.dumps(await client.get_message_by_id(args["message_id"]))

            return json.dumps({"error": f"Unknown action: {action}"})

        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    return handler


def register_seatalk_tool(ctx: Any) -> None:
    """Register the seatalk query tool with the Hermes plugin context."""
    if not hasattr(ctx, "register_tool"):
        logger.debug("seatalk tool: ctx has no register_tool, skipping")
        return
    ctx.register_tool(
        name="seatalk",
        toolset="seatalk-platform",
        schema=SEATALK_TOOL_SCHEMA,
        handler=make_seatalk_tool_handler(),
        is_async=True,
        emoji="💬",
    )
    logger.info("seatalk tool: Registered")
