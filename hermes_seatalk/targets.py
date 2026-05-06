"""SeaTalk target parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeaTalkTarget:
    chat_id: str
    thread_id: str | None
    is_group: bool
    is_email: bool
    account_id: str | None = None


def looks_like_email(value: str) -> bool:
    return "@" in value and "." in value.rsplit("@", 1)[-1]


def parse_seatalk_target(
    target_ref: str,
    known_accounts: set[str] | None = None,
) -> SeaTalkTarget:
    raw = (target_ref or "").strip()
    if raw.startswith("seatalk:"):
        raw = raw.split(":", 1)[1]
    if not raw:
        raise ValueError("SeaTalk target is required")

    account_id = None
    if known_accounts:
        possible_account, separator, rest = raw.partition(":")
        if separator and possible_account in known_accounts:
            account_id = possible_account
            raw = rest.strip()
            if not raw:
                raise ValueError("SeaTalk account-qualified target requires target")

    if raw.startswith("group/"):
        chat_id, thread_id = _split_optional_thread(raw)
        group_id = chat_id[len("group/") :]
        if not group_id:
            raise ValueError("SeaTalk group target requires group id")
        return SeaTalkTarget(
            chat_id=f"group/{group_id}",
            thread_id=thread_id,
            is_group=True,
            is_email=False,
            account_id=account_id,
        )

    chat_id, thread_id = _split_optional_thread(raw)
    is_email = looks_like_email(chat_id)
    return SeaTalkTarget(
        chat_id=chat_id.lower() if is_email else chat_id,
        thread_id=thread_id,
        is_group=False,
        is_email=is_email,
        account_id=account_id,
    )


def format_seatalk_target(chat_id: str, thread_id: str | None = None) -> str:
    target = chat_id.strip()
    if not target:
        raise ValueError("SeaTalk chat_id is required")
    return f"seatalk:{target}:{thread_id}" if thread_id else f"seatalk:{target}"


def _split_optional_thread(value: str) -> tuple[str, str | None]:
    if ":" not in value:
        return value, None
    chat_id, thread_id = value.rsplit(":", 1)
    if not chat_id or not thread_id:
        raise ValueError("SeaTalk target thread format must be <chat_id>:<thread_id>")
    return chat_id, thread_id
