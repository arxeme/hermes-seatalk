"""Clarify card wire format and rendering shared by the adapter and dispatcher."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CLARIFY_CHOICE_VALUE_PREFIX = "stc1:"
CLARIFY_OTHER_VALUE_PREFIX = "stco1:"
CLARIFY_MAX_CHOICES = 4
CLARIFY_OTHER_INDEX = -1
CLARIFY_OTHER_LABEL = "Other\u2026"
CLARIFY_ID_RE = r"[0-9a-f]{10}"
CLARIFY_ID_PATTERN = re.compile(rf"^{CLARIFY_ID_RE}$")
CLARIFY_CHOICE_VALUE_PATTERN = re.compile(
    rf"^{CLARIFY_CHOICE_VALUE_PREFIX}({CLARIFY_ID_RE}):(\d+)$"
)
CLARIFY_OTHER_VALUE_PATTERN = re.compile(
    rf"^{CLARIFY_OTHER_VALUE_PREFIX}({CLARIFY_ID_RE})$"
)
SEATALK_CARD_DESCRIPTION_MAX_CHARS = 1000
# A bare rule would read as a setext heading underline for the line above it.
CLOSED_DIVIDER = "`-----------------------------`"
CHOSEN_OPTION = "\u2705"
UNCHOSEN_OPTION = "\u2b1c"


@dataclass(frozen=True)
class SeaTalkClarifyCard:
    message_id: str
    chat_id: str
    thread_id: str | None
    account_id: str | None


def encode_clarify_choice_value(clarify_id: str, index: int) -> str | None:
    if not CLARIFY_ID_PATTERN.match(clarify_id) or not 0 <= index < CLARIFY_MAX_CHOICES:
        return None
    return f"{CLARIFY_CHOICE_VALUE_PREFIX}{clarify_id}:{index}"


def encode_clarify_other_value(clarify_id: str) -> str | None:
    if not CLARIFY_ID_PATTERN.match(clarify_id):
        return None
    return f"{CLARIFY_OTHER_VALUE_PREFIX}{clarify_id}"


def decode_clarify_value(value: Any) -> tuple[str, int | None] | None:
    if not isinstance(value, str):
        return None
    choice = CLARIFY_CHOICE_VALUE_PATTERN.match(value)
    if choice:
        index = int(choice.group(2))
        return (choice.group(1), index) if index < CLARIFY_MAX_CHOICES else None
    other = CLARIFY_OTHER_VALUE_PATTERN.match(value)
    return (other.group(1), None) if other else None


def build_clarify_elements(
    *,
    question: str,
    choices: list[str],
    clarify_id: str,
) -> list[dict[str, Any]] | None:
    if not 1 <= len(choices) <= CLARIFY_MAX_CHOICES:
        return None
    prompt = (question or "").strip()
    if not prompt or len(prompt) > SEATALK_CARD_DESCRIPTION_MAX_CHARS:
        return None

    buttons = []
    for index, choice in enumerate(choices):
        label = str(choice).strip()
        value = encode_clarify_choice_value(clarify_id, index)
        if not label or value is None:
            return None
        buttons.append({"button_type": "callback", "text": label, "value": value})
    other_value = encode_clarify_other_value(clarify_id)
    if other_value is None:
        return None
    buttons.append({"button_type": "callback", "text": CLARIFY_OTHER_LABEL, "value": other_value})

    elements: list[dict[str, Any]] = [
        {"element_type": "description", "description": {"format": 1, "text": prompt}},
    ]
    elements.extend({"element_type": "button", "button": button} for button in buttons)
    return elements


def build_closed_clarify_elements(
    elements: list[Any],
    chosen_index: int | None,
    status: str | None,
) -> list[dict[str, Any]] | None:
    """get_message echoes a callback button's label but never its value."""
    descriptions: list[dict[str, Any]] = []
    labels: list[str] = []

    for element in elements:
        if not isinstance(element, dict):
            continue
        if element.get("element_type") == "description":
            body = element.get("description")
            text = body.get("text") if isinstance(body, dict) else None
            if isinstance(text, str) and text:
                descriptions.append(
                    {"element_type": "description", "description": {"format": 1, "text": text}}
                )
        elif element.get("element_type") == "button":
            button = element.get("button")
            text = button.get("text") if isinstance(button, dict) else None
            if isinstance(text, str) and text:
                labels.append(text)

    if not labels:
        return None

    chosen = (
        chosen_index % len(labels)
        if chosen_index is not None and -len(labels) <= chosen_index < len(labels)
        else None
    )
    if chosen is None:
        body = f"_{status}_" if status else ""
    else:
        checklist = "\n".join(
            f"{CHOSEN_OPTION if position == chosen else UNCHOSEN_OPTION} {label}"
            for position, label in enumerate(labels)
        )
        body = f"{checklist}\n\n_{status}_" if status else checklist
    return [
        *descriptions,
        {
            "element_type": "description",
            "description": {"format": 1, "text": f"{CLOSED_DIVIDER}\n{body}"},
        },
    ]
