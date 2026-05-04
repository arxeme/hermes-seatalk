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
REQUIRED_ENV = [
    "SEATALK_APP_ID",
    "SEATALK_APP_SECRET",
    "SEATALK_SIGNING_SECRET",
    "SEATALK_MODE",
]
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


def _cfg_value(config: Any, env_name: str, extra_name: str) -> str:
    value = os.getenv(env_name)
    if value is not None:
        return value.strip()
    raw = _extra(config).get(extra_name, "")
    return str(raw).strip() if raw is not None else ""


def _cfg_bool(config: Any, env_name: str, extra_name: str, default: bool) -> bool:
    raw = os.getenv(env_name)
    if raw is None:
        raw = _extra(config).get(extra_name, default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _cfg_float(config: Any, env_name: str, extra_name: str, default: float) -> float:
    raw = _cfg_value(config, env_name, extra_name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_value(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _mode_from_env() -> str:
    return _env_value("SEATALK_MODE").lower()


def _mode_from_config(config: Any) -> str:
    return _cfg_value(config, "SEATALK_MODE", "mode").lower()


def _credentials_from_env() -> bool:
    return all(_env_value(name) for name in REQUIRED_ENV)


def _credentials_from_config(config: Any) -> bool:
    return all(
        _cfg_value(config, env_name, extra_name)
        for env_name, extra_name in (
            ("SEATALK_APP_ID", "app_id"),
            ("SEATALK_APP_SECRET", "app_secret"),
            ("SEATALK_SIGNING_SECRET", "signing_secret"),
            ("SEATALK_MODE", "mode"),
        )
    )


def _webhook_port_from_config(config: Any) -> int | None:
    raw = _cfg_value(config, "SEATALK_WEBHOOK_PORT", "webhook_port") or "8646"
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
    """Return whether env-only plugin requirements are satisfied."""
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        return False

    if not _credentials_from_env():
        return False

    mode = _mode_from_env()
    if mode not in VALID_MODES:
        return False
    if mode == "relay":
        return bool(_env_value("SEATALK_RELAY_URL"))
    # Webhook port has a valid default (8646); port-range validation is deferred
    # to _validate_seatalk_config which receives the full config object.
    return True


def _validate_seatalk_config(config: Any) -> bool:
    """Validate env/config values enough for Hermes to create the adapter."""
    if not _credentials_from_config(config):
        return False

    mode = _mode_from_config(config)
    if mode not in VALID_MODES:
        return False
    if mode == "relay":
        return bool(_cfg_value(config, "SEATALK_RELAY_URL", "relay_url"))
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
        self.app_id = _cfg_value(config, "SEATALK_APP_ID", "app_id")
        self.app_secret = _cfg_value(config, "SEATALK_APP_SECRET", "app_secret")
        self.signing_secret = _cfg_value(config, "SEATALK_SIGNING_SECRET", "signing_secret")
        self.mode = _mode_from_config(config) or "relay"
        self.relay_url = _cfg_value(config, "SEATALK_RELAY_URL", "relay_url")
        self.home_channel = _cfg_value(config, "SEATALK_HOME_CHANNEL", "home_channel")
        self.home_channel_thread_id = _cfg_value(
            config,
            "SEATALK_HOME_CHANNEL_THREAD_ID",
            "home_channel_thread_id",
        )
        self.outbound_coalescing = _cfg_bool(
            config,
            "SEATALK_OUTBOUND_COALESCING",
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
        allow_hosts = _cfg_csv(config, "SEATALK_MEDIA_ALLOW_HOSTS", "media_allow_hosts")
        self._dispatcher = self.extra.get("dispatcher") or SeaTalkEventDispatcher(
            adapter=self,
            client=self.client,
            app_id=self.app_id,
            emit=self.extra.get("message_event_handler"),
            media_allow_hosts=allow_hosts or None,
            debounce_idle_seconds=_cfg_float(
                config,
                "SEATALK_INBOUND_DEBOUNCE_IDLE_SECONDS",
                "inbound_debounce_idle_seconds",
                1.5,
            ),
            debounce_max_seconds=_cfg_float(
                config,
                "SEATALK_INBOUND_DEBOUNCE_MAX_SECONDS",
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
                "SEATALK_OUTBOUND_COALESCING_IDLE_SECONDS",
                "outbound_coalescing_idle_seconds",
                OUTBOUND_COALESCING_IDLE_SECONDS,
            ),
        )

    async def connect(self) -> bool:
        try:
            if self.mode == "webhook":
                self._webhook_server = SeaTalkWebhookServer(
                    host=_cfg_value(self.config, "SEATALK_WEBHOOK_HOST", "webhook_host") or "0.0.0.0",
                    port=_webhook_port_from_config(self.config) or 8646,
                    path=_cfg_value(self.config, "SEATALK_WEBHOOK_PATH", "webhook_path") or "/callback",
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
                    "SEATALK_RELAY_RECONNECT_INITIAL_SECONDS",
                    "relay_reconnect_initial_seconds",
                    1.0,
                ),
                reconnect_max_seconds=_cfg_float(
                    self.config,
                    "SEATALK_RELAY_RECONNECT_MAX_SECONDS",
                    "relay_reconnect_max_seconds",
                    30.0,
                ),
                heartbeat_timeout_seconds=_cfg_float(
                    self.config,
                    "SEATALK_RELAY_HEARTBEAT_TIMEOUT_SECONDS",
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


def _seatalk_setup_wizard() -> None:
    """Interactive setup entry point used by `hermes gateway setup`."""
    from hermes_cli.setup import (
        get_env_value,
        print_header,
        print_info,
        print_success,
        prompt,
        prompt_choice,
        save_env_value,
    )

    print_header("SeaTalk")
    print_info("Configure the SeaTalk platform plugin. Restart the gateway after saving.")

    for env_name, label in (
        ("SEATALK_APP_ID", "SeaTalk app id"),
        ("SEATALK_APP_SECRET", "SeaTalk app secret"),
        ("SEATALK_SIGNING_SECRET", "SeaTalk signing secret"),
    ):
        value = prompt(label, default=get_env_value(env_name) or "")
        if value:
            save_env_value(env_name, value)

    existing_mode = (get_env_value("SEATALK_MODE") or "relay").lower()
    default_index = 1 if existing_mode == "webhook" else 0
    mode_choice = prompt_choice(
        "SeaTalk connection mode",
        ["relay", "webhook"],
        default_index,
    )
    mode = "webhook" if mode_choice == 1 else "relay"
    save_env_value("SEATALK_MODE", mode)

    if mode == "relay":
        relay_url = prompt(
            "SeaTalk relay WebSocket URL",
            default=get_env_value("SEATALK_RELAY_URL") or "",
        )
        if relay_url:
            save_env_value("SEATALK_RELAY_URL", relay_url)
    else:
        for env_name, label, default in (
            ("SEATALK_WEBHOOK_HOST", "Webhook bind host", "0.0.0.0"),
            ("SEATALK_WEBHOOK_PORT", "Webhook port", "8646"),
            ("SEATALK_WEBHOOK_PATH", "Webhook path", "/callback"),
        ):
            value = prompt(label, default=get_env_value(env_name) or default)
            if value:
                save_env_value(env_name, value)
        print_info("Point the SeaTalk Bot App callback URL at this webhook endpoint.")

    for env_name, label in (
        ("SEATALK_HOME_CHANNEL", "Default SeaTalk home channel (optional)"),
        ("SEATALK_HOME_CHANNEL_THREAD_ID", "Default thread id (optional)"),
        ("SEATALK_ALLOWED_USERS", "Allowed users, comma-separated emails (optional)"),
        ("SEATALK_GROUP_ALLOWED_USERS", "Allowed groups, comma-separated group/<id> (optional)"),
        ("SEATALK_REQUIRE_MENTION", "Require bot mention in groups, true/false (optional)"),
    ):
        value = prompt(label, default=get_env_value(env_name) or "")
        if value:
            save_env_value(env_name, value)

    print_success("SeaTalk configuration saved to ~/.hermes/.env")
    print_info("Restart the gateway for changes to take effect: hermes gateway restart")


def _cfg_csv(config: Any, env_name: str, extra_name: str) -> set[str]:
    raw = os.getenv(env_name)
    if raw is None:
        raw_value = _extra(config).get(extra_name)
        if isinstance(raw_value, (list, tuple, set)):
            return {str(item).strip().lower() for item in raw_value if str(item).strip()}
        raw = str(raw_value or "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _patch_cron_scheduler() -> None:
    """Add SeaTalk to cron delivery platform and home target maps."""
    try:
        import cron.scheduler as scheduler
    except ImportError:
        return

    known = getattr(scheduler, "_KNOWN_DELIVERY_PLATFORMS", frozenset())
    if SEATALK_PLATFORM not in known:
        scheduler._KNOWN_DELIVERY_PLATFORMS = frozenset(set(known) | {SEATALK_PLATFORM})

    home_envs = getattr(scheduler, "_HOME_TARGET_ENV_VARS", None)
    if isinstance(home_envs, dict):
        home_envs.setdefault(SEATALK_PLATFORM, "SEATALK_HOME_CHANNEL")


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
    """Read SeaTalk home channel env values from GatewayConfig fallback path."""
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
        home = os.getenv("SEATALK_HOME_CHANNEL", "").strip()
        if not home:
            return None
        return HomeChannel(
            platform=platform,
            chat_id=home,
            name=os.getenv("SEATALK_HOME_CHANNEL_NAME", "SeaTalk Home"),
            thread_id=os.getenv("SEATALK_HOME_CHANNEL_THREAD_ID", "").strip() or None,
        )

    _patched_get_home_channel._seatalk_patched = True  # type: ignore[attr-defined]
    _patched_get_home_channel._seatalk_original = original  # type: ignore[attr-defined]
    GatewayConfig.get_home_channel = _patched_get_home_channel


def _platform_value(platform: Any) -> str:
    return str(getattr(platform, "value", platform)).lower()


def register(ctx: Any) -> None:
    """Plugin entry point called by the Hermes plugin loader."""
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
        allowed_users_env="SEATALK_ALLOWED_USERS",
        allow_all_env="SEATALK_ALLOW_ALL_USERS",
        max_message_length=4000,
        emoji="💬",
        platform_hint=_SEATALK_PLATFORM_HINT,
    )
    setattr(ctx, "_seatalk_platform_registered", True)
