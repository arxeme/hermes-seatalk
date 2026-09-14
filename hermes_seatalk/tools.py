"""SeaTalk lookup + outbound tool for Hermes Agent.

The ``send_message`` action exists because hermes removed the agent-callable core
``send_message`` tool (commit c6c8abbad, in v2026.6.19+): outbound is expected to
come from a platform-native tool instead — the pattern upstream points Yuanbao at
(``yb_send_dm``). Targets are resolved in-plugin, so the model never constructs a
cross-platform target string, and every send is checked against the account's
existing ``allow_from`` / ``group_allow_from`` whitelists.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .client import (
    build_file_message,
    build_image_message,
    build_text_message,
    prepare_outbound_media,
)
from .targets import parse_seatalk_target

logger = logging.getLogger(__name__)

READ_ACTIONS = (
    "group_history",
    "group_info",
    "group_list",
    "thread_history",
    "get_message",
)
ACTIONS = READ_ACTIONS + ("send_message",)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

SEATALK_TOOL_SCHEMA: dict[str, Any] = {
    "name": "seatalk",
    # Keep this tight: a bulky schema can push the whole listing past the
    # tool_search activation threshold, which defers this tool out of the
    # directly-callable set and has been observed to make the model give up on it.
    "description": (
        "SeaTalk lookups (group_history, group_info, group_list, thread_history, "
        "get_message) and sending (send_message). History/thread results resolve "
        "quoted_message. send_message reaches a conversation you are not in — "
        "target is an employee code, an email, or group/<id>; replying to the "
        "message you are handling needs no tool call."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(ACTIONS),
                "description": (
                    "History actions return oldest-to-newest; the first page (no cursor) "
                    "holds the most recent, so follow next_cursor for older ones. "
                    "group_history needs the 'Get Chat History' app permission. "
                    "get_message resolves any message_id or quoted_message_id."
                ),
            },
            "target": {
                "type": "string",
                "description": (
                    "send_message: employee code, email, or group/<id>. Optional "
                    "'<account>:' prefix and ':<thread_id>' suffix."
                ),
            },
            "text": {
                "type": "string",
                "description": "send_message: message text (Markdown).",
            },
            "media_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "send_message: existing local file paths to attach.",
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

    # The plugin can be imported under different package roots (`hermes_seatalk` in tests,
    # `hermes_plugins.<plugin>.hermes_seatalk` when loaded by the gateway), so an isinstance
    # check against a freshly imported class fails on the other module instance. Match the
    # adapter by class name and shape instead.
    for adapter_instance in runner.adapters.values():
        if type(adapter_instance).__name__ != "SeaTalkAdapter":
            continue
        runtimes = getattr(adapter_instance, "_runtimes", None)
        if runtimes is None:
            continue
        key = account_id if account_id else getattr(adapter_instance, "_default_account_id", None)
        runtime = runtimes.get(key)
        if runtime:
            return _loop_local_client(runtime.client)
    return None


def _get_seatalk_tool_account(account_id: str | None = None) -> Any | None:
    """Resolve the account config backing the tool call, for policy checks.

    Kept separate from the client getter so the existing read actions and their
    injected fakes are unaffected.
    """
    try:
        from gateway.run import _gateway_runner_ref
    except ImportError:
        return None

    runner = _gateway_runner_ref()
    if not runner:
        return None
    for adapter_instance in runner.adapters.values():
        if type(adapter_instance).__name__ != "SeaTalkAdapter":
            continue
        runtimes = getattr(adapter_instance, "_runtimes", None)
        if runtimes is None:
            continue
        key = account_id if account_id else getattr(adapter_instance, "_default_account_id", None)
        runtime = runtimes.get(key)
        if runtime:
            return getattr(runtime, "config", None)
    return None


def _allowed(candidates: list[str], allow_from: Any) -> bool:
    """Whitelist match, mirroring the inbound dispatcher's comparison."""
    entries = [str(entry).strip() for entry in (allow_from or ()) if str(entry).strip()]
    if not entries:
        return False
    lowered = {c.lower() for c in candidates if c}
    for entry in entries:
        if entry == "*":
            return True
        if entry.lower() in lowered:
            return True
    return False


def _check_send_allowed(account: Any, target: Any, raw_target: str) -> str | None:
    """Return an error string when *target* is outside the account whitelist.

    The account's inbound whitelists double as the outbound guard: whoever may
    talk to the bot is who the bot may proactively message. Fails closed — an
    empty whitelist rejects rather than allows.
    """
    if account is None:
        return (
            "SeaTalk account config unavailable; refusing to send without a whitelist check"
        )
    if target.is_group:
        group_id = target.chat_id[len("group/"):] if target.chat_id.startswith("group/") else target.chat_id
        if getattr(account, "group_policy", "") == "disabled":
            return f"group sending is disabled for account '{account.account_id}' (group_policy=disabled)"
        if not _allowed([group_id], getattr(account, "group_allow_from", ())):
            return (
                f"group {group_id} is not in group_allow_from for account "
                f"'{account.account_id}'; add it there to allow sending"
            )
        return None
    # DM: accept a match on either the raw target (an email as configured) or the
    # resolved employee code, since allow_from may hold either form.
    if not _allowed([target.chat_id, raw_target], getattr(account, "allow_from", ())):
        return (
            f"target '{raw_target}' is not in allow_from for account "
            f"'{account.account_id}'; add it there to allow sending"
        )
    return None


async def _resolve_send_target(client: Any, raw_target: str, known_accounts: set[str]) -> Any:
    """Parse a target and resolve an email to its employee code."""
    target = parse_seatalk_target(raw_target, known_accounts=known_accounts or None)
    if not target.is_email:
        return target
    resolved = await client.get_employee_code_by_email([target.chat_id])
    employee_code = resolved.get(target.chat_id)
    if not employee_code:
        raise ValueError(
            f"no active SeaTalk employee found for email '{target.chat_id}'"
        )
    return type(target)(
        chat_id=employee_code,
        thread_id=target.thread_id,
        is_group=False,
        is_email=False,
        account_id=target.account_id,
    )


async def _send_payload(client: Any, target: Any, message: dict[str, Any]) -> dict[str, Any]:
    if target.chat_id.startswith("group/"):
        return await client.send_group_chat(
            target.chat_id[len("group/"):], message, target.thread_id
        )
    return await client.send_single_chat(target.chat_id, message, target.thread_id)


async def _do_send(
    client: Any, account: Any, raw_target: str, text: str, media_paths: list[str],
) -> str:
    """Handle the send_message action end to end; returns the JSON tool result."""
    if not raw_target:
        return json.dumps({"error": "target is required for send_message"})
    if not text and not media_paths:
        return json.dumps({"error": "provide text and/or media_paths"})

    known = {getattr(account, "account_id", "")} if account is not None else set()
    known.discard("")
    try:
        target = await _resolve_send_target(client, raw_target, known)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    denied = _check_send_allowed(account, target, raw_target)
    if denied:
        return json.dumps({"error": denied})

    text_format = int(getattr(account, "text_format", 1) or 1)
    sent: list[dict[str, Any]] = []
    if text:
        response = await _send_payload(client, target, build_text_message(text, text_format))
        sent.append({"type": "text", "message_id": _message_id(response)})
    for raw_path in media_paths:
        path = Path(raw_path)
        if not path.is_file():
            return json.dumps({
                "error": f"media path does not exist: {raw_path}",
                "sent": sent,
            })
        media = prepare_outbound_media(path)
        if path.suffix.lower() in _IMAGE_SUFFIXES:
            message = build_image_message(media.base64)
            kind = "image"
        else:
            message = build_file_message(media.base64, media.filename or path.name)
            kind = "file"
        response = await _send_payload(client, target, message)
        sent.append({"type": kind, "path": str(path), "message_id": _message_id(response)})

    return json.dumps({
        "sent": sent,
        "target": {
            "chat_id": target.chat_id,
            "thread_id": target.thread_id,
            "is_group": target.is_group,
        },
    })


def _message_id(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    for key in ("message_id", "messageId", "id"):
        value = response.get(key)
        if value:
            return str(value)
    return None


def _loop_local_client(src: Any) -> Any:
    """Build a fresh client with the source client's credentials.

    The runtime client's aiohttp session is bound to the gateway's event loop, while the
    tool handler runs in the agent's loop - reusing it raises "Timeout context manager
    should be used inside a task". A fresh client creates its session lazily inside the
    handler's own loop. The handler closes clients flagged as tool-owned.
    """
    try:
        client = type(src)(
            src.app_id,
            src.app_secret,
            base_url=src.base_url,
            log_secrets=list(getattr(src, "_log_secrets", []) or []),
        )
    except Exception:  # noqa: BLE001 - fall back to the shared instance
        return src
    client._seatalk_tool_owned = True
    return client


def make_seatalk_tool_handler(get_client: Any = None, get_account: Any = None) -> Any:
    """Create the seatalk tool handler with injectable client/account getters."""
    _get_client = get_client if get_client is not None else _get_seatalk_tool_client
    _get_account = get_account if get_account is not None else _get_seatalk_tool_account

    async def handler(args: dict[str, Any], **_kwargs: Any) -> str:
        action = args.get("action", "")
        account_id = args.get("account_id")
        account = _get_account(account_id=account_id)
        if account is not None and not dict(getattr(account, "tools", {}) or {}).get(action, True):
            return json.dumps({"error": f"action '{action}' is disabled"})
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

            if action == "send_message":
                return await _do_send(
                    client,
                    account,
                    (args.get("target") or "").strip(),
                    args.get("text") or "",
                    list(args.get("media_paths") or []),
                )

            return json.dumps({"error": f"Unknown action: {action}"})

        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})
        finally:
            if getattr(client, "_seatalk_tool_owned", False):
                try:
                    await client.close()
                except Exception:  # noqa: BLE001
                    pass

    return handler


def register_seatalk_tool(ctx: Any) -> None:
    """Register the seatalk tool with the Hermes plugin context."""
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
