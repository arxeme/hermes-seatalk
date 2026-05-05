"""SeaTalk platform plugin entry point for Hermes Agent."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from gateway.config import Platform
    from gateway.platforms.base import BasePlatformAdapter, SendResult
    _HAS_HERMES_BASE = True
except Exception:  # pragma: no cover - lets the plugin import outside Hermes.
    _HAS_HERMES_BASE = False

    class Platform(str):
        pass

    class BasePlatformAdapter:  # type: ignore[no-redef]
        pass

    @dataclass
    class SendResult:  # type: ignore[no-redef]
        success: bool
        message_id: str | None = None
        error: str | None = None
        raw_response: Any = None
        retryable: bool = False

from .client import (
    SeaTalkError,
    SeaTalkOpenAPIClient,
    build_file_message,
    build_image_message,
    build_text_message,
    prepare_outbound_media,
    prepare_outbound_media_bytes,
)
from .coalescer import OutboundCoalescerMap
from .dispatcher import SeaTalkEventDispatcher
from .relay import SeaTalkRelayClient
from .targets import SeaTalkTarget, parse_seatalk_target
from .webhook import SeaTalkWebhookServer


SEATALK_PLATFORM = "seatalk"
SEATALK_PLUGIN_NAME = "seatalk-platform"
VALID_MODES = {"relay", "webhook"}
VALID_DM_POLICIES = {"allowlist", "open", "pairing"}
VALID_GROUP_POLICIES = {"disabled", "allowlist", "open"}
VALID_PROCESSING_INDICATORS = {"typing", "off"}
REQUIRED_ENV = [
    "SEATALK_APP_SECRET",
    "SEATALK_SIGNING_SECRET",
]
INTERNAL_ALLOWED_USERS_ENV = "HERMES_SEATALK_ALLOWED_USERS"
MAX_MESSAGE_LENGTH = 4000
OUTBOUND_COALESCING_IDLE_SECONDS = 1.0

_SEATALK_PLATFORM_HINT = (
    "You are chatting via SeaTalk. Prefer concise plain text. SeaTalk supports "
    "DMs, groups, and group threads; group messages may require mention-based "
    "routing depending on configuration."
)


def _extra(config: Any) -> dict[str, Any]:
    raw = getattr(config, "extra", {}) or {}
    return raw if isinstance(raw, dict) else {}


def _cfg_value(config: Any, extra_name: str) -> str:
    raw = _extra(config).get(extra_name, "")
    return str(raw).strip() if raw is not None else ""


def _cfg_bool(config: Any, extra_name: str, default: bool) -> bool:
    raw = _extra(config).get(extra_name, default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _cfg_float(config: Any, extra_name: str, default: float) -> float:
    raw = _cfg_value(config, extra_name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_value(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _mode_from_config(config: Any) -> str:
    return _cfg_value(config, "mode").lower() or "webhook"


def _policy_from_config(config: Any, extra_name: str, default: str) -> str:
    return _cfg_value(config, extra_name).lower() or default


def _secrets_from_env() -> bool:
    return bool(_env_value("SEATALK_APP_SECRET") and _env_value("SEATALK_SIGNING_SECRET"))


def _credentials_from_config(config: Any) -> bool:
    return bool(_cfg_value(config, "app_id") and _mode_from_config(config) and _secrets_from_env())


def _webhook_port_from_config(config: Any) -> int | None:
    raw = _cfg_value(config, "webhook_port") or "8080"
    try:
        port = int(raw)
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def _message_id(response: dict[str, Any] | None) -> str | None:
    if not isinstance(response, dict):
        return None
    for key in ("message_id", "messageId", "id"):
        value = response.get(key)
        if value:
            return str(value)
    return None


def _platform_instance() -> Any:
    try:
        return Platform(SEATALK_PLATFORM)
    except Exception:  # Direct unit tests may instantiate before registry registration.
        return type("_SeaTalkPlatform", (), {"value": SEATALK_PLATFORM, "name": "SEATALK"})()


def check_seatalk_requirements() -> bool:
    """Return whether dependencies, secrets, and config.yaml values are present."""
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        return False

    config = type("_SeaTalkConfig", (), {"extra": _config_file_extra()})()
    return _validate_seatalk_config(config)


def _validate_seatalk_config(config: Any) -> bool:
    """Validate env/config values enough for Hermes to create the adapter."""
    if not _credentials_from_config(config):
        return False

    mode = _mode_from_config(config)
    if mode not in VALID_MODES:
        return False
    dm_policy = _policy_from_config(config, "dm_policy", "allowlist")
    if dm_policy not in VALID_DM_POLICIES:
        return False
    group_policy = _policy_from_config(config, "group_policy", "disabled")
    if group_policy not in VALID_GROUP_POLICIES:
        return False
    processing_indicator = _policy_from_config(config, "processing_indicator", "typing")
    if processing_indicator not in VALID_PROCESSING_INDICATORS:
        return False
    if dm_policy == "pairing" and group_policy in {"allowlist", "open"}:
        return False
    if mode == "relay":
        return bool(_cfg_value(config, "relay_url"))
    return _webhook_port_from_config(config) is not None


def _is_seatalk_connected(config: Any) -> bool:
    """Hermes startup check; intentionally static, not live adapter health."""
    return _validate_seatalk_config(config)


class SeaTalkAdapter(BasePlatformAdapter):
    """Hermes platform adapter for SeaTalk."""

    def __init__(self, config: Any):
        if _HAS_HERMES_BASE:
            super().__init__(config=config, platform=_platform_instance())
        else:
            self.platform = Platform(SEATALK_PLATFORM)
            self._running = False
        self.config = config
        self.extra = _extra(config)
        _sync_auth_env_from_extra(self.extra)
        self.app_id = _cfg_value(config, "app_id")
        self.app_secret = _env_value("SEATALK_APP_SECRET")
        self.signing_secret = _env_value("SEATALK_SIGNING_SECRET")
        self.mode = _mode_from_config(config)
        self.relay_url = _cfg_value(config, "relay_url")
        self.home_channel = _cfg_value(config, "home_channel")
        self.home_channel_thread_id = _cfg_value(config, "home_channel_thread_id")
        self.processing_indicator = _policy_from_config(config, "processing_indicator", "typing")
        self.outbound_coalescing = _cfg_bool(
            config,
            "outbound_coalescing",
            True,
        )
        self.client = self.extra.get("client") or SeaTalkOpenAPIClient(
            self.app_id,
            self.app_secret,
            log_secrets=[self.signing_secret],
        )
        self.inbound_events: list[tuple[dict[str, Any], str]] = []
        self._seatalk_event_handler = self.extra.get("event_handler")
        allow_hosts = _cfg_csv(config, "media_allow_hosts", lower=True)
        self._dispatcher = self.extra.get("dispatcher") or SeaTalkEventDispatcher(
            adapter=self,
            client=self.client,
            app_id=self.app_id,
            emit=self.extra.get("message_event_handler"),
            media_allow_hosts=allow_hosts or None,
            dm_policy=_policy_from_config(config, "dm_policy", "allowlist"),
            allowlist=_cfg_csv(config, "allow_from", lower=True),
            group_policy=_policy_from_config(config, "group_policy", "disabled"),
            group_allowlist=_cfg_csv(config, "group_allow_from"),
            group_sender_allowlist=_cfg_csv(config, "group_sender_allow_from", lower=True),
            debounce_idle_seconds=_cfg_float(
                config,
                "inbound_debounce_idle_seconds",
                1.5,
            ),
            debounce_max_seconds=_cfg_float(
                config,
                "inbound_debounce_max_seconds",
                5.0,
            ),
        )
        self._webhook_server: SeaTalkWebhookServer | None = None
        self._relay_client: SeaTalkRelayClient | None = None
        self._coalescers = OutboundCoalescerMap(
            send_factory=lambda chat_id, thread_id: (
                lambda text: self._send_text_or_raise(chat_id, text, thread_id)
            ),
            chunk_text=self._split_text,
            max_length=MAX_MESSAGE_LENGTH,
            idle_flush_seconds=_cfg_float(
                config,
                "outbound_coalescing_idle_seconds",
                OUTBOUND_COALESCING_IDLE_SECONDS,
            ),
        )

    async def connect(self) -> bool:
        try:
            if self.mode == "webhook":
                self._webhook_server = SeaTalkWebhookServer(
                    host=_cfg_value(self.config, "webhook_host") or "0.0.0.0",
                    port=_webhook_port_from_config(self.config) or 8080,
                    path=_cfg_value(self.config, "webhook_path") or "/callback",
                    signing_secret=self.signing_secret,
                    dispatch=self._dispatch_event,
                )
                await self._webhook_server.start()
                self._mark_running()
                return True

            self._relay_client = SeaTalkRelayClient(
                relay_url=self.relay_url,
                app_id=self.app_id,
                app_secret=self.app_secret,
                signing_secret=self.signing_secret,
                dispatch=self._dispatch_event,
                reconnect_initial_seconds=_cfg_float(
                    self.config,
                    "relay_reconnect_initial_seconds",
                    1.0,
                ),
                reconnect_max_seconds=_cfg_float(
                    self.config,
                    "relay_reconnect_max_seconds",
                    30.0,
                ),
                heartbeat_timeout_seconds=_cfg_float(
                    self.config,
                    "relay_heartbeat_timeout_seconds",
                    60.0,
                ),
            )
            connected = await self._relay_client.start()
            if connected:
                self._mark_running()
            elif self._relay_client.auth_failed:
                self._mark_fatal("relay_auth_failed", self._relay_client.last_error or "relay auth failed")
            return connected
        except Exception as exc:  # noqa: BLE001
            self._mark_fatal("seatalk_connect_failed", str(exc), retryable=True)
            return False

    async def disconnect(self) -> None:
        flush_inbound = getattr(self._dispatcher, "flush_all", None)
        if flush_inbound:
            await flush_inbound()
        await self.flush_outbound()
        if self._relay_client is not None:
            await self._relay_client.stop()
            self._relay_client = None
        if self._webhook_server is not None:
            await self._webhook_server.stop()
            self._webhook_server = None
        close = getattr(self.client, "close", None)
        if close:
            result = close()
            if asyncio.iscoroutine(result):
                await result
        self._mark_stopped()

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        del reply_to
        try:
            target = await self._resolve_target(chat_id, metadata)
            if self.outbound_coalescing and not (metadata or {}).get("_skip_coalescing"):
                self._coalescers.append(target.chat_id, target.thread_id, content)
                return SendResult(success=True, raw_response={"queued": True})
            return await self._send_text_now(target.chat_id, content, target.thread_id)
        except Exception as exc:  # noqa: BLE001
            return SendResult(success=False, error=str(exc), retryable=isinstance(exc, SeaTalkError))

    async def send_typing(self, chat_id: str, metadata: dict[str, Any] | None = None) -> SendResult:
        try:
            if self.processing_indicator == "off":
                return SendResult(success=True)
            target = await self._resolve_target(chat_id, metadata)
            if target.is_group:
                await self.client.send_group_chat_typing(target.chat_id[len("group/") :], target.thread_id)
            else:
                await self.client.send_single_chat_typing(target.chat_id, target.thread_id)
            return SendResult(success=True)
        except Exception as exc:  # noqa: BLE001
            return SendResult(success=False, error=str(exc))

    async def send_image(
        self,
        chat_id: str,
        image_url: str,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        del reply_to
        try:
            data, _content_type = await self.client.download_media(image_url)
            filename = Path(urlsplit(image_url).path).name or "image"
            media = prepare_outbound_media_bytes(data, filename)
            return await self._send_media_message(
                chat_id,
                build_image_message(media.base64),
                caption=caption,
                metadata=metadata,
            )
        except Exception as exc:  # noqa: BLE001
            return SendResult(success=False, error=str(exc), retryable=isinstance(exc, SeaTalkError))

    async def send_image_file(
        self,
        chat_id: str,
        image_path: str,
        caption: str | None = None,
        reply_to: str | None = None,
        **kwargs: Any,
    ) -> SendResult:
        del reply_to
        try:
            media = prepare_outbound_media(image_path)
            return await self._send_media_message(
                chat_id,
                build_image_message(media.base64),
                caption=caption,
                metadata=kwargs.get("metadata"),
            )
        except Exception as exc:  # noqa: BLE001
            return SendResult(success=False, error=str(exc), retryable=isinstance(exc, SeaTalkError))

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: str | None = None,
        file_name: str | None = None,
        reply_to: str | None = None,
        **kwargs: Any,
    ) -> SendResult:
        del reply_to
        try:
            media = prepare_outbound_media(file_path, file_name=file_name)
            return await self._send_media_message(
                chat_id,
                build_file_message(media.base64, media.filename or file_name or Path(file_path).name or "file"),
                caption=caption,
                metadata=kwargs.get("metadata"),
            )
        except Exception as exc:  # noqa: BLE001
            return SendResult(success=False, error=str(exc), retryable=isinstance(exc, SeaTalkError))

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        target = parse_seatalk_target(chat_id)
        if target.is_group:
            try:
                data = await self.client.get_group_info(target.chat_id[len("group/") :])
                return {
                    "name": data.get("group_name") or target.chat_id,
                    "type": "group",
                    "chat_id": target.chat_id,
                }
            except Exception:  # noqa: BLE001
                pass
        return {
            "name": target.chat_id,
            "type": "group" if target.is_group else "dm",
            "chat_id": target.chat_id,
        }

    async def flush_outbound(self) -> None:
        await self._coalescers.flush_all()

    def set_seatalk_event_handler(self, handler: Any) -> None:
        self._seatalk_event_handler = handler

    async def _dispatch_event(self, event: dict[str, Any], source: str) -> None:
        self.inbound_events.append((event, source))
        handler = self._seatalk_event_handler
        if handler:
            result = handler(event, source)
            if asyncio.iscoroutine(result):
                await result
        await self._dispatcher.dispatch(event, source)
        self._mark_running()

    async def _resolve_target(
        self,
        chat_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> SeaTalkTarget:
        raw_target = (chat_id or "").strip()
        metadata = metadata or {}
        if not raw_target or raw_target == SEATALK_PLATFORM:
            raw_target = self.home_channel
            if not raw_target:
                raise ValueError("SeaTalk home channel is not configured")
        target = parse_seatalk_target(raw_target)
        thread_id = metadata.get("thread_id") or target.thread_id
        if raw_target == self.home_channel and not thread_id:
            thread_id = self.home_channel_thread_id or None
        if target.is_email:
            resolved = await self.client.get_employee_code_by_email([target.chat_id])
            employee_code = resolved.get(target.chat_id)
            if not employee_code:
                raise ValueError(
                    "SeaTalk: no active employee found for email "
                    f"'{target.chat_id}'. Check the email is correct and the account is active "
                    "in your SeaTalk organization."
                )
            target = SeaTalkTarget(
                chat_id=employee_code,
                thread_id=thread_id,
                is_group=False,
                is_email=False,
            )
        elif thread_id != target.thread_id:
            target = SeaTalkTarget(
                chat_id=target.chat_id,
                thread_id=thread_id,
                is_group=target.is_group,
                is_email=target.is_email,
            )
        return target

    async def _send_media_message(
        self,
        chat_id: str,
        message: dict[str, Any],
        *,
        caption: str | None,
        metadata: dict[str, Any] | None,
    ) -> SendResult:
        target = await self._resolve_target(chat_id, metadata)
        if caption:
            caption_result = await self._send_text_now(target.chat_id, caption, target.thread_id)
            if not caption_result.success:
                return caption_result
        response = await self._send_message_payload(target.chat_id, message, target.thread_id)
        return SendResult(success=True, message_id=_message_id(response), raw_response=response)

    async def _send_text_now(self, chat_id: str, content: str, thread_id: str | None) -> SendResult:
        if not content:
            return SendResult(success=True)
        last_response: dict[str, Any] | None = None
        for chunk in self._split_text(content, MAX_MESSAGE_LENGTH):
            last_response = await self._send_message_payload(chat_id, build_text_message(chunk), thread_id)
        return SendResult(
            success=True,
            message_id=_message_id(last_response),
            raw_response=last_response,
        )

    async def _send_text_or_raise(self, chat_id: str, content: str, thread_id: str | None) -> None:
        result = await self._send_text_now(chat_id, content, thread_id)
        if not result.success:
            raise RuntimeError(result.error or "SeaTalk send failed")

    async def _send_message_payload(
        self,
        chat_id: str,
        message: dict[str, Any],
        thread_id: str | None,
    ) -> dict[str, Any]:
        if chat_id.startswith("group/"):
            return await self.client.send_group_chat(chat_id[len("group/") :], message, thread_id)
        return await self.client.send_single_chat(chat_id, message, thread_id)

    def _split_text(self, content: str, max_length: int) -> list[str]:
        truncate = getattr(BasePlatformAdapter, "truncate_message", None)
        if truncate:
            return truncate(content, max_length)
        return [content[i : i + max_length] for i in range(0, len(content), max_length)] or [""]

    def _mark_running(self) -> None:
        mark = getattr(self, "_mark_connected", None)
        if mark:
            mark()
        else:
            self._running = True

    def _mark_stopped(self) -> None:
        mark = getattr(self, "_mark_disconnected", None)
        if mark:
            mark()
        else:
            self._running = False

    def _mark_fatal(self, code: str, message: str, *, retryable: bool = False) -> None:
        mark = getattr(self, "_set_fatal_error", None)
        if mark:
            mark(code, message, retryable=retryable)
        else:
            self._running = False
            self._fatal_error_code = code
            self._fatal_error_message = message


def _raw_config_file() -> dict[str, Any]:
    try:
        import yaml
        from hermes_cli.config import get_config_path
    except Exception:
        return {}

    path = get_config_path()
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _config_file_extra() -> dict[str, Any]:
    config = _raw_config_file()
    platforms = config.get("platforms")
    if not isinstance(platforms, dict):
        return {}
    seatalk = platforms.get(SEATALK_PLATFORM)
    if not isinstance(seatalk, dict):
        return {}
    extra = seatalk.get("extra")
    return extra if isinstance(extra, dict) else {}


def _ensure_seatalk_extra(config: dict[str, Any]) -> dict[str, Any]:
    platforms = config.setdefault("platforms", {})
    if not isinstance(platforms, dict):
        platforms = {}
        config["platforms"] = platforms
    seatalk = platforms.setdefault(SEATALK_PLATFORM, {})
    if not isinstance(seatalk, dict):
        seatalk = {}
        platforms[SEATALK_PLATFORM] = seatalk
    seatalk["enabled"] = True
    extra = seatalk.setdefault("extra", {})
    if not isinstance(extra, dict):
        extra = {}
        seatalk["extra"] = extra
    return extra


def _coerce_csv(raw: Any, *, lower: bool = False) -> str:
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple, set)):
        values = [str(item).strip() for item in raw if str(item).strip()]
    else:
        values = [item.strip() for item in str(raw).split(",") if item.strip()]
    if lower:
        values = [item.lower() for item in values]
    return ",".join(values)


def _csv_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _set_optional(extra: dict[str, Any], key: str, value: str) -> None:
    value = value.strip()
    if value:
        extra[key] = value
    else:
        extra.pop(key, None)


def _set_optional_csv(extra: dict[str, Any], key: str, value: str) -> None:
    values = _csv_list(value)
    if values:
        extra[key] = values
    else:
        extra.pop(key, None)


def _sync_auth_env_from_extra(extra: dict[str, Any]) -> None:
    dm_policy = str(extra.get("dm_policy") or "allowlist").strip().lower()
    group_policy = str(extra.get("group_policy") or "disabled").strip().lower()
    allowlist = _csv_list(extra.get("allow_from"))

    if dm_policy == "open" or group_policy in {"allowlist", "open"}:
        os.environ[INTERNAL_ALLOWED_USERS_ENV] = "*"
        return

    values: list[str] = []
    if dm_policy == "allowlist":
        values.extend(allowlist)
    deduped = list(dict.fromkeys(item.strip() for item in values if item and item.strip()))
    if deduped:
        os.environ[INTERNAL_ALLOWED_USERS_ENV] = ",".join(deduped)
    else:
        os.environ.pop(INTERNAL_ALLOWED_USERS_ENV, None)


def _seatalk_setup_wizard() -> None:
    """Interactive setup entry point used by `hermes gateway setup`."""
    from hermes_cli.setup import (
        get_env_value,
        print_header,
        print_info,
        print_success,
        prompt,
        prompt_choice,
        save_config,
        save_env_value,
    )

    print_header("SeaTalk")
    print_info("Configure the SeaTalk platform plugin. Restart the gateway after saving.")

    raw_config = _raw_config_file()
    extra = _ensure_seatalk_extra(raw_config)

    app_id = prompt("SeaTalk app id", default=str(extra.get("app_id") or ""))
    _set_optional(extra, "app_id", app_id)

    for env_name, label in (
        ("SEATALK_APP_SECRET", "SeaTalk app secret"),
        ("SEATALK_SIGNING_SECRET", "SeaTalk signing secret"),
    ):
        value = prompt(label, default=get_env_value(env_name) or "")
        if value:
            save_env_value(env_name, value)

    existing_mode = str(extra.get("mode") or "webhook").lower()
    default_index = 1 if existing_mode == "webhook" else 0
    mode_choice = prompt_choice(
        "SeaTalk connection mode",
        ["relay", "webhook"],
        default_index,
    )
    mode = "webhook" if mode_choice == 1 else "relay"
    extra["mode"] = mode

    if mode == "relay":
        relay_url = prompt(
            "SeaTalk relay WebSocket URL",
            default=str(extra.get("relay_url") or ""),
        )
        _set_optional(extra, "relay_url", relay_url)
        for stale_key in ("webhook_host", "webhook_port", "webhook_path"):
            extra.pop(stale_key, None)
    else:
        extra.pop("relay_url", None)
        for key, label, default in (
            ("webhook_host", "Webhook bind host", "0.0.0.0"),
            ("webhook_port", "Webhook port", "8080"),
            ("webhook_path", "Webhook path", "/callback"),
        ):
            value = prompt(label, default=str(extra.get(key) or default))
            _set_optional(extra, key, value)
        print_info("Point the SeaTalk Bot App callback URL at this webhook endpoint.")

    for key, label in (
        ("home_channel", "Default SeaTalk home channel (optional)"),
        ("home_channel_thread_id", "Default thread id (optional)"),
    ):
        value = prompt(label, default=str(extra.get(key) or ""))
        _set_optional(extra, key, value)

    dm_policy_existing = str(extra.get("dm_policy") or "allowlist").lower()
    dm_policy_index = {"allowlist": 0, "open": 1, "pairing": 2}.get(dm_policy_existing, 0)
    dm_policy_choice = prompt_choice(
        "DM policy",
        ["allowlist", "open", "pairing"],
        dm_policy_index,
    )
    extra["dm_policy"] = ["allowlist", "open", "pairing"][dm_policy_choice]

    allowed = prompt(
        "DM allowed users, comma-separated emails or employee codes",
        default=_coerce_csv(extra.get("allow_from")),
    )
    _set_optional_csv(extra, "allow_from", allowed)

    group_policy_existing = str(extra.get("group_policy") or "disabled").lower()
    group_policy_index = {"disabled": 0, "allowlist": 1, "open": 2}.get(group_policy_existing, 0)
    group_policy_choice = prompt_choice(
        "Group policy",
        ["disabled", "allowlist", "open"],
        group_policy_index,
    )
    group_policy = ["disabled", "allowlist", "open"][group_policy_choice]
    if extra["dm_policy"] == "pairing" and group_policy in {"allowlist", "open"}:
        print_info("DM pairing cannot be combined with enabled group access; group policy remains disabled.")
        group_policy = "disabled"
    extra["group_policy"] = group_policy
    if group_policy == "allowlist":
        groups = prompt(
            "Allowed groups, comma-separated group ids",
            default=_coerce_csv(extra.get("group_allow_from")),
        )
        _set_optional_csv(extra, "group_allow_from", groups)
    else:
        extra.pop("group_allow_from", None)

    if group_policy in {"allowlist", "open"}:
        group_senders = prompt(
            "Group sender allowlist, comma-separated emails or employee codes (optional)",
            default=_coerce_csv(extra.get("group_sender_allow_from")),
        )
        _set_optional_csv(extra, "group_sender_allow_from", group_senders)
    else:
        extra.pop("group_sender_allow_from", None)

    processing_indicator_existing = str(extra.get("processing_indicator") or "typing").lower()
    processing_indicator_index = 1 if processing_indicator_existing == "off" else 0
    processing_indicator_choice = prompt_choice(
        "Processing indicator",
        ["typing", "off"],
        processing_indicator_index,
    )
    extra["processing_indicator"] = "off" if processing_indicator_choice == 1 else "typing"

    save_config(raw_config)
    _sync_auth_env_from_extra(extra)
    print_success("SeaTalk configuration saved to ~/.hermes/config.yaml; secrets saved to ~/.hermes/.env")
    print_info("Restart the gateway for changes to take effect: hermes gateway restart")


def _cfg_csv(config: Any, extra_name: str, *, lower: bool = False) -> set[str]:
    csv = _coerce_csv(_extra(config).get(extra_name), lower=lower)
    return {item.strip() for item in csv.split(",") if item.strip()}


def _patch_cron_scheduler() -> None:
    """Add SeaTalk to cron delivery platform and home target maps."""
    try:
        import cron.scheduler as scheduler
    except ImportError:
        return

    known = getattr(scheduler, "_KNOWN_DELIVERY_PLATFORMS", frozenset())
    if SEATALK_PLATFORM not in known:
        scheduler._KNOWN_DELIVERY_PLATFORMS = frozenset(set(known) | {SEATALK_PLATFORM})

    original_chat_id = getattr(scheduler, "_get_home_target_chat_id", None)
    if callable(original_chat_id) and not getattr(original_chat_id, "_seatalk_patched", False):
        def _patched_home_target_chat_id(platform_name: str) -> str:
            if platform_name.lower() == SEATALK_PLATFORM:
                return str(_config_file_extra().get("home_channel") or "").strip()
            return original_chat_id(platform_name)

        _patched_home_target_chat_id._seatalk_patched = True  # type: ignore[attr-defined]
        _patched_home_target_chat_id._seatalk_original = original_chat_id  # type: ignore[attr-defined]
        scheduler._get_home_target_chat_id = _patched_home_target_chat_id

    original_thread_id = getattr(scheduler, "_get_home_target_thread_id", None)
    if callable(original_thread_id) and not getattr(original_thread_id, "_seatalk_patched", False):
        def _patched_home_target_thread_id(platform_name: str) -> str | None:
            if platform_name.lower() == SEATALK_PLATFORM:
                return str(_config_file_extra().get("home_channel_thread_id") or "").strip() or None
            return original_thread_id(platform_name)

        _patched_home_target_thread_id._seatalk_patched = True  # type: ignore[attr-defined]
        _patched_home_target_thread_id._seatalk_original = original_thread_id  # type: ignore[attr-defined]
        scheduler._get_home_target_thread_id = _patched_home_target_thread_id


def _patch_send_message_tool() -> None:
    """Inject SeaTalk target parsing into ``send_message``."""
    try:
        import tools.send_message_tool as send_message_tool
    except ImportError:
        return

    original = send_message_tool._parse_target_ref
    if getattr(original, "_seatalk_patched", False):
        return

    def _patched_parse(platform_name: str, target_ref: str):
        if platform_name == SEATALK_PLATFORM:
            try:
                target = parse_seatalk_target(target_ref)
            except ValueError:
                return None, None, False
            return target.chat_id, target.thread_id, True
        return original(platform_name, target_ref)

    _patched_parse._seatalk_patched = True  # type: ignore[attr-defined]
    _patched_parse._seatalk_original = original  # type: ignore[attr-defined]
    send_message_tool._parse_target_ref = _patched_parse


def _patch_send_to_platform() -> None:
    """Route SeaTalk send_message calls through the live SeaTalk adapter."""
    try:
        import tools.send_message_tool as send_message_tool
    except ImportError:
        return

    original = send_message_tool._send_to_platform
    if getattr(original, "_seatalk_patched", False):
        return

    async def _patched_send_to_platform(platform, pconfig, chat_id, message, thread_id=None, media_files=None):
        if _platform_value(platform) == SEATALK_PLATFORM:
            return await _seatalk_send_to_platform(
                platform,
                chat_id,
                message,
                thread_id=thread_id,
                media_files=media_files or [],
            )
        return await original(
            platform,
            pconfig,
            chat_id,
            message,
            thread_id=thread_id,
            media_files=media_files,
        )

    _patched_send_to_platform._seatalk_patched = True  # type: ignore[attr-defined]
    _patched_send_to_platform._seatalk_original = original  # type: ignore[attr-defined]
    send_message_tool._send_to_platform = _patched_send_to_platform


async def _seatalk_send_to_platform(
    platform: Any,
    chat_id: str,
    message: str,
    *,
    thread_id: str | None = None,
    media_files: list[tuple[str, bool]] | None = None,
) -> dict[str, Any]:
    """SeaTalk-specific send path that preserves thread and native media."""
    try:
        from gateway.run import _gateway_runner_ref
        from gateway.platforms.base import BasePlatformAdapter
        from gateway.platform_registry import platform_registry
    except Exception as exc:  # noqa: BLE001
        return {"error": f"SeaTalk send unavailable: {exc}"}

    runner = _gateway_runner_ref()
    if not runner:
        return {"error": "No gateway runner. Is the gateway running?"}

    runtime_adapter = runner.adapters.get(platform)
    if runtime_adapter is None:
        return {"error": "No live SeaTalk adapter. Is the gateway running with SeaTalk connected?"}

    metadata = {"thread_id": thread_id} if thread_id else None
    results: list[Any] = []
    if message:
        entry = platform_registry.get(SEATALK_PLATFORM)
        max_len = entry.max_message_length if entry and entry.max_message_length else MAX_MESSAGE_LENGTH
        for chunk in BasePlatformAdapter.truncate_message(message, max_len):
            result = await runtime_adapter.send(chat_id=chat_id, content=chunk, metadata=metadata)
            if not getattr(result, "success", False):
                return {"error": f"SeaTalk send failed: {getattr(result, 'error', 'unknown')}"}
            results.append(result)

    for media_path, _is_voice in media_files or []:
        ext = Path(media_path).suffix.lower()
        if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            result = await runtime_adapter.send_image_file(chat_id, media_path, caption="", metadata=metadata)
        else:
            result = await runtime_adapter.send_document(chat_id, media_path, caption="", metadata=metadata)
        if not getattr(result, "success", False):
            return {"error": f"SeaTalk media send failed: {getattr(result, 'error', 'unknown')}"}
        results.append(result)

    message_id = getattr(results[-1], "message_id", None) if results else None
    return {"success": True, "message_id": message_id}


def _patch_home_channel() -> None:
    """Read SeaTalk home channel values from ``platforms.seatalk.extra``."""
    try:
        from gateway.config import GatewayConfig, HomeChannel
    except Exception:
        return

    original = GatewayConfig.get_home_channel
    if getattr(original, "_seatalk_patched", False):
        return

    def _patched_get_home_channel(self, platform):
        result = original(self, platform)
        if result is not None:
            return result
        if _platform_value(platform) != SEATALK_PLATFORM:
            return None
        try:
            platform_config = self.platforms.get(_platform_instance())
            extra = getattr(platform_config, "extra", {}) or {}
        except Exception:
            extra = {}
        home = str(extra.get("home_channel") or "").strip()
        if not home:
            return None
        return HomeChannel(
            platform=platform,
            chat_id=home,
            name=str(extra.get("home_channel_name") or "SeaTalk Home"),
            thread_id=str(extra.get("home_channel_thread_id") or "").strip() or None,
        )

    _patched_get_home_channel._seatalk_patched = True  # type: ignore[attr-defined]
    _patched_get_home_channel._seatalk_original = original  # type: ignore[attr-defined]
    GatewayConfig.get_home_channel = _patched_get_home_channel


def _platform_value(platform: Any) -> str:
    return str(getattr(platform, "value", platform)).lower()


def register(ctx: Any) -> None:
    """Plugin entry point called by the Hermes plugin loader."""
    _sync_auth_env_from_extra(_config_file_extra())
    _patch_cron_scheduler()
    _patch_send_message_tool()
    _patch_send_to_platform()
    _patch_home_channel()

    if getattr(ctx, "_seatalk_platform_registered", False):
        return
    ctx.register_platform(
        name=SEATALK_PLATFORM,
        label="SeaTalk",
        adapter_factory=lambda cfg: SeaTalkAdapter(cfg),
        check_fn=check_seatalk_requirements,
        validate_config=_validate_seatalk_config,
        is_connected=_is_seatalk_connected,
        required_env=REQUIRED_ENV,
        install_hint="Install aiohttp>=3.9 and configure SeaTalk credentials.",
        setup_fn=_seatalk_setup_wizard,
        allowed_users_env=INTERNAL_ALLOWED_USERS_ENV,
        max_message_length=4000,
        emoji="💬",
        platform_hint=_SEATALK_PLATFORM_HINT,
    )
    setattr(ctx, "_seatalk_platform_registered", True)
