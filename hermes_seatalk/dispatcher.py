"""SeaTalk inbound event normalization and dispatch."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from gateway.config import Platform
    from gateway.platforms.base import (
        MessageEvent,
        MessageType,
        cache_document_from_bytes,
        cache_image_from_bytes,
        cache_video_from_bytes,
    )
    from gateway.session import SessionSource
except Exception:  # pragma: no cover - lets unit tests import outside Hermes.
    from enum import Enum

    class Platform(str):  # type: ignore[no-redef]
        pass

    class MessageType(Enum):  # type: ignore[no-redef]
        TEXT = "text"
        PHOTO = "photo"
        VIDEO = "video"
        DOCUMENT = "document"

    @dataclass
    class SessionSource:  # type: ignore[no-redef]
        platform: Any
        chat_id: str
        chat_name: str | None = None
        chat_type: str = "dm"
        user_id: str | None = None
        user_name: str | None = None
        thread_id: str | None = None
        user_id_alt: str | None = None
        message_id: str | None = None

    @dataclass
    class MessageEvent:  # type: ignore[no-redef]
        text: str
        message_type: MessageType = MessageType.TEXT
        source: SessionSource | None = None
        raw_message: Any = None
        message_id: str | None = None
        media_urls: list[str] = field(default_factory=list)
        media_types: list[str] = field(default_factory=list)
        reply_to_message_id: str | None = None
        reply_to_text: str | None = None

    def cache_image_from_bytes(data: bytes, ext: str = ".jpg") -> str:  # type: ignore[no-redef]
        del data
        return f"/tmp/seatalk-image{ext}"

    def cache_video_from_bytes(data: bytes, ext: str = ".mp4") -> str:  # type: ignore[no-redef]
        del data
        return f"/tmp/seatalk-video{ext}"

    def cache_document_from_bytes(data: bytes, filename: str) -> str:  # type: ignore[no-redef]
        del data
        return f"/tmp/{filename or 'seatalk-document'}"


logger = logging.getLogger(__name__)

SUPPORTED_MESSAGE_EVENTS = {
    "message_from_bot_subscriber",
    "new_mentioned_message_received_from_group_chat",
    "new_message_received_from_thread",
}
LOG_ONLY_EVENTS = {
    "new_bot_subscriber",
    "bot_added_to_group_chat",
    "bot_removed_from_group_chat",
}
DEFAULT_DEDUP_TTL_SECONDS = 30 * 60
DEFAULT_DEDUP_MAX_SIZE = 1000
DEFAULT_DEBOUNCE_IDLE_SECONDS = 1.5
DEFAULT_DEBOUNCE_MAX_SECONDS = 5.0
DEFAULT_MEDIA_ALLOW_HOSTS = {"openapi.seatalk.io"}


@dataclass
class _InboundPart:
    source: SessionSource
    text: str
    message_id: str | None
    raw_message: dict[str, Any]
    media_urls: list[str] = field(default_factory=list)
    media_types: list[str] = field(default_factory=list)
    media_errors: list[str] = field(default_factory=list)
    reply_to_message_id: str | None = None
    reply_to_text: str | None = None


@dataclass
class _DebounceBuffer:
    parts: list[_InboundPart] = field(default_factory=list)
    idle_task: asyncio.Task[None] | None = None
    hard_task: asyncio.Task[None] | None = None


class SeaTalkEventDispatcher:
    """Convert SeaTalk callback payloads into Hermes ``MessageEvent`` objects."""

    def __init__(
        self,
        *,
        adapter: Any,
        client: Any,
        app_id: str,
        emit: Any | None = None,
        media_allow_hosts: set[str] | None = None,
        dedup_ttl_seconds: float = DEFAULT_DEDUP_TTL_SECONDS,
        dedup_max_size: int = DEFAULT_DEDUP_MAX_SIZE,
        debounce_idle_seconds: float = DEFAULT_DEBOUNCE_IDLE_SECONDS,
        debounce_max_seconds: float = DEFAULT_DEBOUNCE_MAX_SECONDS,
        now_fn: Any = time.time,
    ):
        self.adapter = adapter
        self.client = client
        self.app_id = app_id
        self.emit = emit
        self.media_allow_hosts = {
            host.strip().lower()
            for host in (media_allow_hosts or DEFAULT_MEDIA_ALLOW_HOSTS)
            if host and host.strip()
        }
        self.dedup_ttl_seconds = dedup_ttl_seconds
        self.dedup_max_size = dedup_max_size
        self.debounce_idle_seconds = debounce_idle_seconds
        self.debounce_max_seconds = debounce_max_seconds
        self._now = now_fn
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._buffers: dict[str, _DebounceBuffer] = {}
        self._group_allowlist: set[str] = _csv_env("SEATALK_GROUP_ALLOWED_USERS")

    async def dispatch(self, payload: dict[str, Any], ingress: str) -> None:
        """Normalize and schedule one SeaTalk event from webhook or relay."""
        event_type = str(payload.get("event_type") or "")
        if event_type in LOG_ONLY_EVENTS:
            logger.info("SeaTalk log-only event: %s", event_type)
            return
        if event_type not in SUPPORTED_MESSAGE_EVENTS:
            logger.info("SeaTalk unknown event type: %s", event_type or "<missing>")
            return

        dedup_key = self._dedup_key(payload)
        if not self._record_event(dedup_key):
            logger.info("SeaTalk duplicate event dropped: %s", dedup_key)
            return

        part = await self._normalize(payload, ingress)
        if part is None:
            return

        key = self._debounce_key(part)
        if self.debounce_idle_seconds <= 0 and self.debounce_max_seconds <= 0:
            await self._emit_parts([part])
            return

        buffer = self._buffers.setdefault(key, _DebounceBuffer())
        buffer.parts.append(part)
        if buffer.idle_task is not None:
            buffer.idle_task.cancel()
        buffer.idle_task = asyncio.create_task(self._flush_after(key, self.debounce_idle_seconds))
        if buffer.hard_task is None:
            buffer.hard_task = asyncio.create_task(self._flush_after(key, self.debounce_max_seconds))

    async def flush_all(self) -> None:
        """Flush all pending debounce buffers."""
        for key in list(self._buffers):
            await self._flush_key(key)

    def _dedup_key(self, payload: dict[str, Any]) -> str:
        app_id = str(payload.get("app_id") or self.app_id or "")
        event_id = str(payload.get("event_id") or "")
        if not event_id:
            event = payload.get("event")
            if isinstance(event, dict):
                message = event.get("message")
                if isinstance(message, dict):
                    event_id = str(message.get("message_id") or "")
        return f"{app_id}:{event_id or id(payload)}"

    def _record_event(self, key: str) -> bool:
        now = self._now()
        cutoff = now - self.dedup_ttl_seconds
        for seen_key, seen_at in list(self._seen.items()):
            if seen_at < cutoff:
                self._seen.pop(seen_key, None)
            else:
                break
        if key in self._seen:
            return False
        self._seen[key] = now
        while len(self._seen) > self.dedup_max_size:
            self._seen.popitem(last=False)
        return True

    async def _normalize(self, payload: dict[str, Any], ingress: str) -> _InboundPart | None:
        event_type = str(payload.get("event_type") or "")
        event = payload.get("event")
        if not isinstance(event, dict):
            logger.info("SeaTalk malformed event: event_type=%s reason=missing_event", event_type)
            return None

        if event_type == "message_from_bot_subscriber":
            return await self._normalize_dm(payload, event, ingress)
        return await self._normalize_group(payload, event, ingress)

    async def _normalize_dm(
        self,
        payload: dict[str, Any],
        event: dict[str, Any],
        ingress: str,
    ) -> _InboundPart | None:
        employee_code = _str_or_none(event.get("employee_code"))
        message = event.get("message")
        if not employee_code or not isinstance(message, dict):
            logger.info("SeaTalk malformed DM event dropped")
            return None

        email = _normalize_email(event.get("email"))
        message_id = _str_or_none(message.get("message_id")) or _str_or_none(payload.get("event_id"))
        thread_id = _str_or_none(message.get("thread_id"))
        text, media_urls, media_types, media_errors = await self._resolve_message_content(message)
        reply_to_id, reply_to_text, quoted_media, quoted_types = await self._resolve_quoted(message)
        media_urls.extend(quoted_media)
        media_types.extend(quoted_types)
        if reply_to_text:
            text = f"{reply_to_text}\n{text}" if text else reply_to_text
        if not text and not media_urls:
            logger.info("SeaTalk empty DM event dropped")
            return None

        source = SessionSource(
            platform=_seatalk_platform(),
            chat_id=employee_code,
            chat_name=email or employee_code,
            chat_type="dm",
            user_id=email or employee_code,
            user_name=_user_name(employee_code, email),
            thread_id=thread_id,
            user_id_alt=employee_code,
            message_id=message_id,
        )
        return _InboundPart(
            source=source,
            text=text,
            message_id=message_id,
            raw_message={"payload": payload, "ingress": ingress, "seatalk_media_errors": media_errors},
            media_urls=media_urls,
            media_types=media_types,
            media_errors=media_errors,
            reply_to_message_id=reply_to_id,
            reply_to_text=reply_to_text,
        )

    async def _normalize_group(
        self,
        payload: dict[str, Any],
        event: dict[str, Any],
        ingress: str,
    ) -> _InboundPart | None:
        group_id = _str_or_none(event.get("group_id"))
        message = event.get("message")
        if not group_id or not isinstance(message, dict):
            logger.info("SeaTalk malformed group event dropped")
            return None

        sender = message.get("sender")
        if not isinstance(sender, dict):
            logger.info("SeaTalk malformed group sender dropped")
            return None
        if sender.get("sender_type") == 2:
            logger.info("SeaTalk self-message dropped: channel=group/%s", group_id)
            return None

        chat_id = f"group/{group_id}"
        if self._group_allowlist and chat_id not in self._group_allowlist:
            logger.warning("SeaTalk group rejected: channel=%s reason=group_not_allowed", chat_id)
            return None

        employee_code = _str_or_none(sender.get("employee_code"))
        if not employee_code:
            logger.info("SeaTalk malformed group sender dropped")
            return None
        email = _normalize_email(sender.get("email"))
        message_id = _str_or_none(message.get("message_id")) or _str_or_none(payload.get("event_id"))
        thread_id = _str_or_none(message.get("thread_id"))
        text, media_urls, media_types, media_errors = await self._resolve_message_content(message)
        reply_to_id, reply_to_text, quoted_media, quoted_types = await self._resolve_quoted(message)
        media_urls.extend(quoted_media)
        media_types.extend(quoted_types)
        if reply_to_text:
            text = f"{reply_to_text}\n{text}" if text else reply_to_text
        if not text and not media_urls:
            logger.info("SeaTalk empty group event dropped: channel=%s", chat_id)
            return None

        source = SessionSource(
            platform=_seatalk_platform(),
            chat_id=chat_id,
            chat_name=group_id,
            chat_type="group",
            user_id=email or employee_code,
            user_name=_user_name(employee_code, email),
            thread_id=thread_id,
            user_id_alt=employee_code,
            message_id=message_id,
        )
        return _InboundPart(
            source=source,
            text=text,
            message_id=message_id,
            raw_message={"payload": payload, "ingress": ingress, "seatalk_media_errors": media_errors},
            media_urls=media_urls,
            media_types=media_types,
            media_errors=media_errors,
            reply_to_message_id=reply_to_id,
            reply_to_text=reply_to_text,
        )

    async def _resolve_message_content(
        self,
        message: dict[str, Any],
    ) -> tuple[str, list[str], list[str], list[str]]:
        tag = str(message.get("tag") or "")
        if tag == "text":
            text = message.get("text")
            if isinstance(text, dict):
                return str(text.get("plain_text") or text.get("content") or ""), [], [], []
            return "", [], [], []
        if tag in {"image", "file", "video"}:
            placeholder = {"image": "<media:image>", "file": "<media:document>", "video": "<media:video>"}[tag]
            url = _media_url(message, tag)
            if not url:
                return placeholder, [], [], [f"{tag}: missing media url"]
            try:
                media_path, media_type = await self._download_media(tag, url, message)
                return placeholder, [media_path], [media_type], []
            except Exception as exc:  # noqa: BLE001
                logger.warning("SeaTalk inbound media download failed: tag=%s error=%s", tag, exc)
                return placeholder, [], [], [f"{tag}: {exc}"]
        if tag == "combined_forwarded_chat_history":
            content = message.get("combined_forwarded_chat_history")
            lines: list[str] = []
            if isinstance(content, dict):
                for item in content.get("content") or []:
                    if isinstance(item, dict):
                        text, _, _, _ = await self._resolve_message_content(item)
                        if text:
                            lines.append(text)
            return ("[Forwarded messages]\n" + "\n".join(lines)).strip(), [], [], []
        return f"<unsupported:{tag or 'unknown'}>", [], [], []

    async def _resolve_quoted(self, message: dict[str, Any]) -> tuple[str | None, str | None, list[str], list[str]]:
        quoted_id = _str_or_none(message.get("quoted_message_id"))
        if not quoted_id:
            return None, None, [], []
        get_message = getattr(self.client, "get_message_by_id", None)
        if not get_message:
            return quoted_id, None, [], []
        try:
            quoted = await get_message(quoted_id)
            if not isinstance(quoted, dict):
                return quoted_id, None, [], []
            sender = quoted.get("sender")
            sender_name = "unknown"
            if isinstance(sender, dict):
                sender_code = _str_or_none(sender.get("employee_code")) or "unknown"
                sender_email = _normalize_email(sender.get("email"))
                sender_name = _user_name(sender_code, sender_email)
            text, media_urls, media_types, _errors = await self._resolve_message_content(quoted)
            return quoted_id, f"[Quoted from {sender_name}: {text}]", media_urls, media_types
        except Exception as exc:  # noqa: BLE001
            logger.warning("SeaTalk quoted message resolve failed: id=%s error=%s", quoted_id, exc)
            return quoted_id, None, [], []

    async def _download_media(self, tag: str, url: str, message: dict[str, Any]) -> tuple[str, str]:
        parsed = urlsplit(url)
        if parsed.scheme != "https":
            raise ValueError(f"only https media URLs are allowed ({parsed.scheme or 'missing'} URL)")
        if parsed.hostname is None or parsed.hostname.lower() not in self.media_allow_hosts:
            raise ValueError(f"media host is not allowed ({parsed.hostname or 'missing'})")
        download = getattr(self.client, "download_media", None)
        if not download:
            raise RuntimeError("SeaTalk client does not support media download")
        raw, content_type = await download(url)
        ext = Path(parsed.path).suffix or _extension_from_content_type(content_type)
        if tag == "image":
            return cache_image_from_bytes(raw, ext or ".jpg"), "image"
        if tag == "video":
            return cache_video_from_bytes(raw, ext or ".mp4"), "video"
        filename = "document"
        file_data = message.get("file")
        if isinstance(file_data, dict):
            filename = str(file_data.get("filename") or filename)
        return cache_document_from_bytes(raw, filename), "document"

    async def _flush_after(self, key: str, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            await self._flush_key(key)
        except asyncio.CancelledError:
            return

    async def _flush_key(self, key: str) -> None:
        buffer = self._buffers.pop(key, None)
        if buffer is None:
            return
        for task in (buffer.idle_task, buffer.hard_task):
            if task is not None:
                task.cancel()
        await self._emit_parts(buffer.parts)

    async def _emit_parts(self, parts: list[_InboundPart]) -> None:
        if not parts:
            return
        first = parts[0]
        text = "\n".join(part.text for part in parts if part.text).strip()
        media_urls: list[str] = []
        media_types: list[str] = []
        media_errors: list[str] = []
        for part in parts:
            media_urls.extend(part.media_urls)
            media_types.extend(part.media_types)
            media_errors.extend(part.media_errors)
        message_type = _message_type(media_types)
        event = MessageEvent(
            text=text,
            message_type=message_type,
            source=first.source,
            raw_message={
                "seatalk_events": [part.raw_message for part in parts],
                "seatalk_media_errors": media_errors,
            },
            message_id=parts[-1].message_id,
            media_urls=media_urls,
            media_types=media_types,
            reply_to_message_id=first.reply_to_message_id,
            reply_to_text=first.reply_to_text,
        )
        if self.emit is not None:
            result = self.emit(event)
        else:
            result = self.adapter.handle_message(event)
        if asyncio.iscoroutine(result):
            await result

    def _debounce_key(self, part: _InboundPart) -> str:
        source = part.source
        if source.chat_type == "dm":
            return ":".join([
                self.app_id,
                source.user_id_alt or source.user_id or "",
                source.thread_id or "",
            ])
        return ":".join([
            self.app_id,
            source.chat_id,
            source.user_id_alt or source.user_id or "",
            source.thread_id or "",
        ])


def _seatalk_platform() -> Any:
    try:
        return Platform("seatalk")
    except Exception:
        return _FallbackPlatform()


@dataclass(frozen=True)
class _FallbackPlatform:
    value: str = "seatalk"

    def __str__(self) -> str:
        return self.value


def _message_type(media_types: list[str]) -> MessageType:
    if not media_types:
        return MessageType.TEXT
    if media_types[0] == "image":
        return MessageType.PHOTO
    if media_types[0] == "video":
        return MessageType.VIDEO
    return MessageType.DOCUMENT


def _media_url(message: dict[str, Any], tag: str) -> str | None:
    data = message.get(tag)
    if isinstance(data, dict):
        return _str_or_none(data.get("content"))
    return None


def _extension_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    return mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ""


def _normalize_email(value: Any) -> str | None:
    text = _str_or_none(value)
    return text.lower() if text and "@" in text else None


def _user_name(employee_code: str, email: str | None) -> str:
    return f"{employee_code} ({email})" if email else employee_code


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _csv_env(name: str) -> set[str]:
    return {item.strip() for item in os.getenv(name, "").split(",") if item.strip()}
