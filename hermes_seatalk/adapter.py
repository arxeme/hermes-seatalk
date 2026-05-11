"""SeaTalk platform plugin entry point for Hermes Agent."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import aiohttp

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

from .tools import register_seatalk_tool
from .client import (
    SeaTalkError,
    SeaTalkNetworkError,
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
from .webhook import SeaTalkWebhookAccount, SeaTalkWebhookServer


logger = logging.getLogger(__name__)
SEATALK_PLATFORM = "seatalk"
SEATALK_PLUGIN_NAME = "seatalk-platform"
VALID_MODES = {"relay", "webhook"}
VALID_DM_POLICIES = {"allowlist", "open"}
VALID_GROUP_POLICIES = {"disabled", "allowlist", "open"}
VALID_PROCESSING_INDICATORS = {"typing", "off"}
REQUIRED_ENV: list[str] = []
INTERNAL_ALLOW_ALL_ENV = "HERMES_SEATALK_ALLOW_ALL"
MAX_MESSAGE_LENGTH = 4000
OUTBOUND_COALESCING_IDLE_SECONDS = 1.0
ACCOUNT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")

_SEATALK_PLATFORM_HINT = (
    "You are chatting via SeaTalk. Prefer concise plain text. SeaTalk supports "
    "DMs, groups, and group threads; group messages may require mention-based "
    "routing depending on configuration."
)


@dataclass(frozen=True)
class SeaTalkAccountConfig:
    account_id: str
    enabled: bool
    app_id: str
    app_secret: str
    signing_secret: str
    mode: str
    relay_url: str = ""
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080
    webhook_path: str = "/callback"
    dm_policy: str = "allowlist"
    allow_from: tuple[str, ...] = ()
    group_policy: str = "disabled"
    group_allow_from: tuple[str, ...] = ()
    group_sender_allow_from: tuple[str, ...] = ()
    processing_indicator: str = "typing"
    media_allow_hosts: tuple[str, ...] = ()
    outbound_coalescing: bool = True


@dataclass
class SeaTalkAccountRuntime:
    config: SeaTalkAccountConfig
    client: Any
    dispatcher: SeaTalkEventDispatcher
    coalescers: OutboundCoalescerMap
    relay_client: SeaTalkRelayClient | None = None
    relay_monitor_task: asyncio.Task[None] | None = None
    webhook_server: SeaTalkWebhookServer | None = None
    state: str = "stopped"
    auth_failed: bool = False
    last_error: str | None = None


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


def _text_value(raw: Any) -> str:
    return str(raw).strip() if raw is not None else ""


def _mode_from_config(config: Any) -> str:
    return _cfg_value(config, "mode").lower() or "webhook"


def _policy_from_config(config: Any, extra_name: str, default: str) -> str:
    return _cfg_value(config, extra_name).lower() or default


def _secrets_from_env() -> bool:
    return bool(_env_value("SEATALK_APP_SECRET") and _env_value("SEATALK_SIGNING_SECRET"))


def _credentials_from_config(config: Any) -> bool:
    return bool(
        _cfg_value(config, "app_id")
        and _cfg_value(config, "app_secret")
        and _cfg_value(config, "signing_secret")
        and _cfg_value(config, "mode")
    )


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


def _account_qualified_target(account_id: str | None, chat_id: str) -> str:
    if account_id:
        return f"{account_id}:{chat_id}"
    return chat_id


def _platform_instance() -> Any:
    try:
        return Platform(SEATALK_PLATFORM)
    except Exception:  # Direct unit tests may instantiate before registry registration.
        return type("_SeaTalkPlatform", (), {"value": SEATALK_PLATFORM, "name": "SEATALK"})()


def _is_enabled(raw: Any, default: bool = True) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _merge_account_config(base: dict[str, Any], account: dict[str, Any]) -> dict[str, Any]:
    defaults = {key: value for key, value in base.items() if key != "accounts"}
    merged = dict(defaults)
    merged.update(account)
    return merged


def _accounts_from_extra(extra: dict[str, Any]) -> dict[str, SeaTalkAccountConfig]:
    if not isinstance(extra, dict):
        raise ValueError("SeaTalk extra config must be a mapping")
    accounts = extra.get("accounts")
    if accounts is None:
        return {}
    if not isinstance(accounts, dict) or not accounts:
        raise ValueError("SeaTalk accounts config is required")

    parsed: dict[str, SeaTalkAccountConfig] = {}
    seen_app_ids: set[str] = set()
    for account_id_raw, raw_account in accounts.items():
        account_id = str(account_id_raw).strip()
        if not ACCOUNT_ID_RE.fullmatch(account_id):
            raise ValueError(f"Invalid SeaTalk account id: {account_id_raw!r}")
        if raw_account is None:
            raw_account = {}
        if not isinstance(raw_account, dict):
            raise ValueError(f"SeaTalk account {account_id} must be a mapping")

        merged = _merge_account_config(extra, raw_account)
        if not _is_enabled(merged.get("enabled"), True):
            continue

        config = _build_account_config(account_id, merged)
        if config.app_id in seen_app_ids:
            raise ValueError(f"Duplicate SeaTalk app_id: {config.app_id}")
        seen_app_ids.add(config.app_id)
        parsed[account_id] = config

    if not parsed:
        raise ValueError("SeaTalk requires at least one enabled account")
    return parsed


def _build_account_config(account_id: str, data: dict[str, Any]) -> SeaTalkAccountConfig:
    app_id = _text_value(data.get("app_id"))
    app_secret = _text_value(data.get("app_secret"))
    signing_secret = _text_value(data.get("signing_secret"))
    mode = _text_value(data.get("mode")).lower()
    if not app_id or not app_secret or not signing_secret or not mode:
        raise ValueError(f"SeaTalk account {account_id} is missing required credentials or mode")
    if mode not in VALID_MODES:
        raise ValueError(f"SeaTalk account {account_id} has invalid mode: {mode}")

    dm_policy = _text_value(data.get("dm_policy")).lower() or "allowlist"
    if dm_policy not in VALID_DM_POLICIES:
        raise ValueError(f"SeaTalk account {account_id} has invalid dm_policy: {dm_policy}")
    group_policy = _text_value(data.get("group_policy")).lower() or "disabled"
    if group_policy not in VALID_GROUP_POLICIES:
        raise ValueError(f"SeaTalk account {account_id} has invalid group_policy: {group_policy}")
    processing_indicator = _text_value(data.get("processing_indicator")).lower() or "typing"
    if processing_indicator not in VALID_PROCESSING_INDICATORS:
        raise ValueError(
            f"SeaTalk account {account_id} has invalid processing_indicator: {processing_indicator}"
        )

    relay_url = _text_value(data.get("relay_url"))
    if mode == "relay" and not relay_url:
        raise ValueError(f"SeaTalk account {account_id} relay_url is required in relay mode")

    webhook_port = _coerce_webhook_port(data.get("webhook_port"))
    webhook_path = _text_value(data.get("webhook_path")) or "/callback"
    if mode == "webhook" and webhook_port is None:
        raise ValueError(f"SeaTalk account {account_id} has invalid webhook_port")
    if mode == "webhook" and (not webhook_path.startswith("/") or any(ch.isspace() for ch in webhook_path)):
        raise ValueError(f"SeaTalk account {account_id} has invalid webhook_path")

    group_allow_from = tuple(_csv_list(data.get("group_allow_from")))
    if any(value.startswith("group/") for value in group_allow_from):
        raise ValueError("SeaTalk group_allow_from values must be raw group ids without group/ prefix")

    return SeaTalkAccountConfig(
        account_id=account_id,
        enabled=True,
        app_id=app_id,
        app_secret=app_secret,
        signing_secret=signing_secret,
        mode=mode,
        relay_url=relay_url,
        webhook_host=_text_value(data.get("webhook_host")) or "0.0.0.0",
        webhook_port=webhook_port or 8080,
        webhook_path=webhook_path,
        dm_policy=dm_policy,
        allow_from=tuple(_csv_list(data.get("allow_from"))),
        group_policy=group_policy,
        group_allow_from=group_allow_from,
        group_sender_allow_from=tuple(_csv_list(data.get("group_sender_allow_from"))),
        processing_indicator=processing_indicator,
        media_allow_hosts=tuple(_csv_list(data.get("media_allow_hosts"))),
        outbound_coalescing=_is_enabled(data.get("outbound_coalescing"), True),
    )


def _build_all_secrets(accounts: dict[str, SeaTalkAccountConfig]) -> list[str]:
    values: list[str] = []
    for account in accounts.values():
        values.extend([account.app_secret, account.signing_secret])
    return list(dict.fromkeys(value for value in values if value))


def _coerce_webhook_port(raw: Any) -> int | None:
    if raw in (None, ""):
        return 8080
    try:
        port = int(raw)
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def check_seatalk_requirements() -> bool:
    """Return whether the plugin's Python dependencies are importable."""
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        return False
    return True


def _validate_seatalk_config(config: Any) -> bool:
    """Validate env/config values enough for Hermes to create the adapter."""
    if not _is_enabled(getattr(config, "enabled", None), True):
        return True
    try:
        _accounts_from_extra(_extra(config))
    except ValueError:
        return False
    return True


def _is_seatalk_connected(config: Any) -> bool:
    """Hermes startup check; intentionally static, not live adapter health."""
    return _validate_seatalk_config(config)


def _remember_event_employee_email(client: Any, payload: dict[str, Any]) -> None:
    remember = getattr(client, "remember_employee_email", None)
    if not callable(remember):
        return
    event = payload.get("event")
    if not isinstance(event, dict):
        event = payload
    candidates: list[tuple[Any, Any]] = [
        (event.get("email"), event.get("employee_code")),
    ]
    direct_sender = event.get("sender")
    if isinstance(direct_sender, dict):
        candidates.append((direct_sender.get("email"), direct_sender.get("employee_code")))
    message = event.get("message")
    if isinstance(message, dict):
        sender = message.get("sender")
        if isinstance(sender, dict):
            candidates.append((sender.get("email"), sender.get("employee_code")))
    for email, employee_code in candidates:
        remember(email, employee_code)


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
        self.inbound_events: list[tuple[dict[str, Any], str]] = []
        self._seatalk_event_handler = self.extra.get("event_handler")
        self.accounts = _accounts_from_extra(self.extra)
        all_secrets = _build_all_secrets(self.accounts)
        self._runtimes = {
            account_id: self._build_runtime(account_config, all_secrets)
            for account_id, account_config in self.accounts.items()
        }
        self._default_account_id = self._select_default_account_id()

    def _select_default_account_id(self) -> str:
        if not self._runtimes:
            return ""
        if "default" in self._runtimes:
            return "default"
        return sorted(self._runtimes)[0]

    def _build_runtime(
        self,
        account_config: SeaTalkAccountConfig,
        all_secrets: list[str],
    ) -> SeaTalkAccountRuntime:
        clients = self.extra.get("clients") if isinstance(self.extra.get("clients"), dict) else {}
        client = clients.get(account_config.account_id) if isinstance(clients, dict) else None
        if client is None:
            client = SeaTalkOpenAPIClient(
                account_config.app_id,
                account_config.app_secret,
                log_secrets=all_secrets,
            )

        dispatchers = self.extra.get("dispatchers") if isinstance(self.extra.get("dispatchers"), dict) else {}
        dispatcher = dispatchers.get(account_config.account_id) if isinstance(dispatchers, dict) else None
        if dispatcher is None:
            dispatcher = SeaTalkEventDispatcher(
                adapter=self,
                client=client,
                app_id=account_config.app_id,
                account_id=account_config.account_id,
                emit=self.extra.get("message_event_handler"),
                media_allow_hosts=set(account_config.media_allow_hosts) or None,
                dm_policy=account_config.dm_policy,
                allowlist={item.lower() for item in account_config.allow_from},
                group_policy=account_config.group_policy,
                group_allowlist=set(account_config.group_allow_from),
                group_sender_allowlist={item.lower() for item in account_config.group_sender_allow_from},
                debounce_idle_seconds=_cfg_float(
                    self.config,
                    "inbound_debounce_idle_seconds",
                    1.5,
                ),
                debounce_max_seconds=_cfg_float(
                    self.config,
                    "inbound_debounce_max_seconds",
                    5.0,
                ),
            )

        coalescers = OutboundCoalescerMap(
            send_factory=lambda chat_id, thread_id, runtime_client=client: (
                lambda text: self._send_text_or_raise_for_client(
                    runtime_client,
                    chat_id,
                    text,
                    thread_id,
                )
            ),
            chunk_text=self._split_text,
            max_length=MAX_MESSAGE_LENGTH,
            idle_flush_seconds=_cfg_float(
                self.config,
                "outbound_coalescing_idle_seconds",
                OUTBOUND_COALESCING_IDLE_SECONDS,
            ),
        )
        return SeaTalkAccountRuntime(
            config=account_config,
            client=client,
            dispatcher=dispatcher,
            coalescers=coalescers,
        )

    async def connect(self) -> bool:
        if not self._runtimes:
            logger.warning(
                "SeaTalk plugin is installed but no accounts are configured. "
                "Run `hermes gateway setup` to configure a SeaTalk account."
            )
            self._mark_running()
            return True
        try:
            results: list[bool] = []
            webhook_groups: dict[tuple[str, int, str], list[SeaTalkAccountRuntime]] = {}
            for runtime in self._runtimes.values():
                if runtime.config.mode == "webhook":
                    account = runtime.config
                    webhook_groups.setdefault(
                        (account.webhook_host, account.webhook_port, account.webhook_path),
                        [],
                    ).append(runtime)
                else:
                    results.append(await self._connect_runtime(runtime))
            for group in webhook_groups.values():
                results.append(await self._connect_webhook_group(group))
            self._refresh_platform_state()
            return any(results)
        except Exception as exc:  # noqa: BLE001
            self._mark_fatal("seatalk_connect_failed", str(exc), retryable=True)
            return False

    async def _connect_webhook_group(self, runtimes: list[SeaTalkAccountRuntime]) -> bool:
        first = runtimes[0].config
        try:
            server = SeaTalkWebhookServer(
                host=first.webhook_host,
                port=first.webhook_port,
                path=first.webhook_path,
                accounts=[
                    SeaTalkWebhookAccount(
                        account_id=runtime.config.account_id,
                        app_id=runtime.config.app_id,
                        signing_secret=runtime.config.signing_secret,
                        dispatch=lambda event, source, account_id=runtime.config.account_id: (
                            self._dispatch_runtime_event(account_id, event, source)
                        ),
                    )
                    for runtime in runtimes
                ],
            )
            await server.start()
            for runtime in runtimes:
                runtime.webhook_server = server
                self._set_runtime_state(runtime, "running")
            return True
        except Exception as exc:  # noqa: BLE001
            for runtime in runtimes:
                self._set_runtime_state(runtime, "auth_failed", str(exc))
            return False

    async def _connect_runtime(self, runtime: SeaTalkAccountRuntime) -> bool:
        account = runtime.config
        try:
            runtime.relay_client = SeaTalkRelayClient(
                relay_url=account.relay_url,
                app_id=account.app_id,
                app_secret=account.app_secret,
                signing_secret=account.signing_secret,
                dispatch=lambda event, source, account_id=account.account_id: (
                    self._dispatch_runtime_event(account_id, event, source)
                ),
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
                    75.0,
                ),
            )
            connected = await runtime.relay_client.start(
                timeout=_cfg_float(self.config, "relay_connect_timeout_seconds", 5.0)
            )
            if connected:
                self._set_runtime_state(runtime, "running")
            elif runtime.relay_client.auth_failed:
                self._set_runtime_state(
                    runtime,
                    "auth_failed",
                    runtime.relay_client.last_error or "relay auth failed",
                )
            else:
                self._set_runtime_state(
                    runtime,
                    "retrying",
                    runtime.relay_client.last_error or "relay connection pending",
                )
            runtime.relay_monitor_task = asyncio.create_task(self._monitor_relay_runtime(runtime))
            return runtime.state in {"running", "retrying"}
        except Exception as exc:  # noqa: BLE001
            self._set_runtime_state(runtime, "auth_failed", str(exc))
            return False

    async def _monitor_relay_runtime(self, runtime: SeaTalkAccountRuntime) -> None:
        try:
            while runtime.relay_client is not None:
                client = runtime.relay_client
                if client.auth_failed:
                    self._set_runtime_state(runtime, "auth_failed", client.last_error or "relay auth failed")
                    self._refresh_platform_state()
                    return
                if client.connected.is_set():
                    if runtime.state != "running":
                        self._set_runtime_state(runtime, "running")
                        self._refresh_platform_state()
                elif runtime.state == "running" or client.last_error:
                    self._set_runtime_state(runtime, "retrying", client.last_error or "relay reconnecting")
                    self._refresh_platform_state()
                task = getattr(client, "_task", None)
                if task is not None and task.done():
                    if client.auth_failed:
                        self._set_runtime_state(runtime, "auth_failed", client.last_error or "relay auth failed")
                    elif runtime.state == "running":
                        self._set_runtime_state(runtime, "retrying", client.last_error or "relay reconnecting")
                    self._refresh_platform_state()
                    return
                await asyncio.sleep(_cfg_float(self.config, "relay_state_poll_seconds", 0.1))
        except asyncio.CancelledError:
            return

    async def disconnect(self) -> None:
        stopped_webhook_servers: set[int] = set()
        for runtime in self._runtimes.values():
            flush_inbound = getattr(runtime.dispatcher, "flush_all", None)
            if flush_inbound:
                await flush_inbound()
            await runtime.coalescers.flush_all()
            if runtime.relay_monitor_task is not None:
                runtime.relay_monitor_task.cancel()
                await asyncio.gather(runtime.relay_monitor_task, return_exceptions=True)
                runtime.relay_monitor_task = None
            if runtime.relay_client is not None:
                await runtime.relay_client.stop()
                runtime.relay_client = None
            if runtime.webhook_server is not None:
                server_id = id(runtime.webhook_server)
                if server_id not in stopped_webhook_servers:
                    await runtime.webhook_server.stop()
                    stopped_webhook_servers.add(server_id)
                runtime.webhook_server = None
            close = getattr(runtime.client, "close", None)
            if close:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            self._set_runtime_state(runtime, "stopped")
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
            runtime = self._runtime_for_target(target)
            skip_coalescing = bool((metadata or {}).get("_skip_coalescing"))
            should_coalesce = (
                runtime.config.outbound_coalescing
                and not skip_coalescing
                and len(content) <= MAX_MESSAGE_LENGTH
            )
            if should_coalesce:
                runtime.coalescers.append(target.chat_id, target.thread_id, content)
                return SendResult(success=True, raw_response={"queued": True})
            return await self._send_text_now_for_client(runtime.client, target.chat_id, content, target.thread_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SeaTalk send failed: chat_id=%s error=%s", chat_id, exc)
            return SendResult(success=False, error=str(exc), retryable=isinstance(exc, SeaTalkError))

    async def send_typing(self, chat_id: str, metadata: dict[str, Any] | None = None) -> SendResult:
        try:
            target = await self._resolve_target(chat_id, metadata)
            runtime = self._runtime_for_target(target)
            if runtime.config.processing_indicator == "off":
                return SendResult(success=True)
            if target.is_group:
                await runtime.client.send_group_chat_typing(target.chat_id[len("group/") :], target.thread_id)
            else:
                await runtime.client.send_single_chat_typing(target.chat_id, target.thread_id)
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
            target = await self._resolve_target(chat_id, metadata)
            runtime = self._runtime_for_target(target)
            data = await _fetch_outbound_media_bytes(runtime.client, image_url)
            filename = Path(urlsplit(image_url).path).name or "image"
            media = prepare_outbound_media_bytes(data, filename)
            return await self._send_media_message_to_target(
                runtime,
                target,
                build_image_message(media.base64),
                caption=caption,
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
        target = parse_seatalk_target(chat_id, known_accounts=set(self._runtimes))
        account_id = target.account_id or self._default_account_id
        runtime = self._runtime_for_account(account_id)
        if target.is_group:
            try:
                data = await runtime.client.get_group_info(target.chat_id[len("group/") :])
                return {
                    "name": data.get("group_name") or target.chat_id,
                    "type": "group",
                    "chat_id": _account_qualified_target(target.account_id, target.chat_id),
                }
            except Exception:  # noqa: BLE001
                pass
        return {
            "name": target.chat_id,
            "type": "group" if target.is_group else "dm",
            "chat_id": _account_qualified_target(target.account_id, target.chat_id),
        }

    async def flush_outbound(self) -> None:
        for runtime in self._runtimes.values():
            await runtime.coalescers.flush_all()

    def set_seatalk_event_handler(self, handler: Any) -> None:
        self._seatalk_event_handler = handler

    async def _dispatch_event(self, event: dict[str, Any], source: str) -> None:
        await self._dispatch_runtime_event(self._default_account_id, event, source)

    async def _dispatch_runtime_event(self, account_id: str, event: dict[str, Any], source: str) -> None:
        runtime = self._runtimes[account_id]
        payload_app_id = str(event.get("app_id") or "")
        if source == "relay" and payload_app_id and payload_app_id != runtime.config.app_id:
            logger.warning(
                "SeaTalk relay event dropped: account_id=%s reason=app_id_mismatch expected=%s got=%s",
                account_id,
                runtime.config.app_id,
                payload_app_id,
            )
            return
        _remember_event_employee_email(runtime.client, event)
        self.inbound_events.append((event, source))
        handler = self._seatalk_event_handler
        if handler:
            result = handler(event, source)
            if asyncio.iscoroutine(result):
                await result
        await runtime.dispatcher.dispatch(event, source)
        self._set_runtime_state(runtime, "running")
        self._refresh_platform_state()

    async def _resolve_target(
        self,
        chat_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> SeaTalkTarget:
        if not self._runtimes:
            raise ValueError("SeaTalk has no accounts configured")
        raw_target = (chat_id or "").strip()
        metadata = metadata or {}
        if not raw_target or raw_target == SEATALK_PLATFORM:
            raw_target = self._configured_home_target()
            if not raw_target:
                raise ValueError("SeaTalk home channel is not configured")
        target = parse_seatalk_target(raw_target, known_accounts=set(self._runtimes))
        account_id = self._select_target_account_id(target, metadata)
        thread_id = metadata.get("thread_id") or target.thread_id
        if raw_target == self._configured_home_target() and not thread_id:
            thread_id = os.getenv("SEATALK_HOME_CHANNEL_THREAD_ID", "").strip() or None
        if target.is_email:
            runtime = self._runtime_for_account(account_id)
            if runtime.state not in {"running", "retrying"}:
                raise ValueError(
                    f"SeaTalk account '{account_id}' is not ready (state={runtime.state}); "
                    "cannot resolve email target"
                )
            try:
                resolved = await runtime.client.get_employee_code_by_email([target.chat_id])
            except SeaTalkNetworkError as exc:
                raise SeaTalkNetworkError(
                    "SeaTalk email lookup failed while resolving "
                    f"'{target.chat_id}' to employee_code for account '{account_id}': {exc}"
                ) from exc
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
                account_id=account_id,
            )
        elif thread_id != target.thread_id:
            target = SeaTalkTarget(
                chat_id=target.chat_id,
                thread_id=thread_id,
                is_group=target.is_group,
                is_email=target.is_email,
                account_id=account_id,
            )
        elif target.account_id != account_id:
            target = SeaTalkTarget(
                chat_id=target.chat_id,
                thread_id=target.thread_id,
                is_group=target.is_group,
                is_email=target.is_email,
                account_id=account_id,
            )
        return target

    def _configured_home_target(self) -> str:
        return os.getenv("SEATALK_HOME_CHANNEL", "").strip()

    def _select_target_account_id(self, target: SeaTalkTarget, metadata: dict[str, Any]) -> str:
        metadata_account_id = str(metadata.get("seatalk_account_id") or "").strip()
        account_id = metadata_account_id or target.account_id or self._default_account_id
        self._runtime_for_account(account_id)
        return account_id

    def _runtime_for_target(self, target: SeaTalkTarget) -> SeaTalkAccountRuntime:
        return self._runtime_for_account(target.account_id or self._default_account_id)

    def _runtime_for_account(self, account_id: str) -> SeaTalkAccountRuntime:
        try:
            return self._runtimes[account_id]
        except KeyError as exc:
            raise ValueError(f"Unknown SeaTalk account id: {account_id}") from exc

    async def _send_media_message(
        self,
        chat_id: str,
        message: dict[str, Any],
        *,
        caption: str | None,
        metadata: dict[str, Any] | None,
    ) -> SendResult:
        target = await self._resolve_target(chat_id, metadata)
        runtime = self._runtime_for_target(target)
        return await self._send_media_message_to_target(
            runtime,
            target,
            message,
            caption=caption,
        )

    async def _send_media_message_to_target(
        self,
        runtime: SeaTalkAccountRuntime,
        target: SeaTalkTarget,
        message: dict[str, Any],
        *,
        caption: str | None,
    ) -> SendResult:
        if caption:
            caption_result = await self._send_text_now_for_client(
                runtime.client,
                target.chat_id,
                caption,
                target.thread_id,
            )
            if not caption_result.success:
                return caption_result
        try:
            response = await self._send_message_payload_for_client(
                runtime.client, target.chat_id, message, target.thread_id,
            )
            return SendResult(success=True, message_id=_message_id(response), raw_response=response)
        except Exception as exc:  # noqa: BLE001
            # Match openclaw outbound.ts:69-76 — on media send failure, fall back to
            # a markdown text notice (format=2) so the user gets some reply rather
            # than silent loss.
            fallback_text = f"[Media send failed: {exc}]"
            try:
                fallback_response = await self._send_message_payload_for_client(
                    runtime.client,
                    target.chat_id,
                    build_text_message(fallback_text, fmt=2),
                    target.thread_id,
                )
            except Exception as fallback_exc:  # noqa: BLE001
                logger.warning(
                    "SeaTalk media send + fallback both failed: media=%s fallback=%s",
                    exc,
                    fallback_exc,
                )
                return SendResult(
                    success=False,
                    error=f"{exc} (fallback failed: {fallback_exc})",
                    retryable=isinstance(exc, SeaTalkError),
                )
            return SendResult(
                success=True,
                message_id=_message_id(fallback_response),
                raw_response={"fallback_text": fallback_text, "raw": fallback_response},
            )

    async def _send_text_now_for_client(
        self,
        client: Any,
        chat_id: str,
        content: str,
        thread_id: str | None,
    ) -> SendResult:
        if not content:
            return SendResult(success=True)
        last_response: dict[str, Any] | None = None
        for chunk in self._split_text(content, MAX_MESSAGE_LENGTH):
            last_response = await self._send_message_payload_for_client(client, chat_id, build_text_message(chunk), thread_id)
        return SendResult(
            success=True,
            message_id=_message_id(last_response),
            raw_response=last_response,
        )

    async def _send_text_or_raise_for_client(
        self,
        client: Any,
        chat_id: str,
        content: str,
        thread_id: str | None,
    ) -> None:
        if not content:
            return
        for chunk in self._split_text(content, MAX_MESSAGE_LENGTH):
            await self._send_message_payload_for_client(client, chat_id, build_text_message(chunk), thread_id)

    async def _send_message_payload_for_client(
        self,
        client: Any,
        chat_id: str,
        message: dict[str, Any],
        thread_id: str | None,
    ) -> dict[str, Any]:
        if chat_id.startswith("group/"):
            return await client.send_group_chat(chat_id[len("group/") :], message, thread_id)
        return await client.send_single_chat(chat_id, message, thread_id)

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

    def _set_runtime_state(
        self,
        runtime: SeaTalkAccountRuntime,
        state: str,
        error: str | None = None,
    ) -> None:
        runtime.state = state
        runtime.auth_failed = state == "auth_failed"
        runtime.last_error = error
        logger.info(
            "SeaTalk account runtime state changed: account_id=%s state=%s error=%s",
            runtime.config.account_id,
            state,
            error or "",
        )

    def _refresh_platform_state(self) -> None:
        runtimes = list(self._runtimes.values())
        if any(runtime.state in {"running", "retrying"} for runtime in runtimes):
            self._mark_running()
            return
        if runtimes and all(runtime.state == "auth_failed" for runtime in runtimes):
            self._mark_fatal("seatalk_all_accounts_failed", "all SeaTalk accounts failed")


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


def _known_account_ids_from_extra(extra: dict[str, Any]) -> set[str]:
    accounts = extra.get("accounts")
    if not isinstance(accounts, dict):
        return set()
    return {str(account_id) for account_id in accounts if str(account_id).strip()}


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


def _seatalk_setup_wizard() -> None:
    """Interactive setup entry point used by `hermes gateway setup`."""
    from hermes_cli.setup import (
        print_header,
        print_info,
        print_success,
        prompt,
        prompt_choice,
        save_config,
    )
    from hermes_cli.config import get_env_value, save_env_value

    print_header("SeaTalk")
    print_info("Configure SeaTalk accounts. Values are saved to ~/.hermes/config.yaml.")
    print_info("SeaTalk app_secret and signing_secret are stored in config.yaml; protect this file.")

    raw_config = _raw_config_file()
    extra = _ensure_seatalk_extra(raw_config)
    accounts = extra.setdefault("accounts", {})
    if not isinstance(accounts, dict):
        accounts = {}
        extra["accounts"] = accounts

    account_ids = sorted(str(account_id) for account_id in accounts)
    default_account_id = "default" if not account_ids else account_ids[0]
    account_id = prompt("SeaTalk account id", default=default_account_id).strip() or default_account_id
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        raise ValueError(f"Invalid SeaTalk account id: {account_id!r}")

    action = prompt_choice(
        "SeaTalk account action",
        ["add/edit", "disable", "remove"],
        0,
    )
    if action == 2:
        accounts.pop(account_id, None)
        save_config(raw_config)
        print_success(f"SeaTalk account '{account_id}' removed from ~/.hermes/config.yaml")
        return

    account = accounts.setdefault(account_id, {})
    if not isinstance(account, dict):
        account = {}
        accounts[account_id] = account
    if action == 1:
        account["enabled"] = False
        save_config(raw_config)
        print_success(f"SeaTalk account '{account_id}' disabled in ~/.hermes/config.yaml")
        return

    account["enabled"] = True
    for key, label in (
        ("app_id", "SeaTalk app id"),
        ("app_secret", "SeaTalk app secret"),
        ("signing_secret", "SeaTalk signing secret"),
    ):
        value = prompt(label, default=str(account.get(key) or ""))
        _set_optional(account, key, value)

    existing_mode = str(account.get("mode") or "webhook").lower()
    default_index = 1 if existing_mode == "webhook" else 0
    mode_choice = prompt_choice(
        "SeaTalk connection mode",
        ["relay", "webhook"],
        default_index,
    )
    mode = "webhook" if mode_choice == 1 else "relay"
    account["mode"] = mode

    if mode == "relay":
        relay_url = prompt(
            "SeaTalk relay WebSocket URL",
            default=str(account.get("relay_url") or ""),
        )
        _set_optional(account, "relay_url", relay_url)
        for stale_key in ("webhook_host", "webhook_port", "webhook_path"):
            account.pop(stale_key, None)
    else:
        account.pop("relay_url", None)
        for key, label, default in (
            ("webhook_host", "Webhook bind host", "0.0.0.0"),
            ("webhook_port", "Webhook port", "8080"),
            ("webhook_path", "Webhook path", "/callback"),
        ):
            value = prompt(label, default=str(account.get(key) or default))
            _set_optional(account, key, value)
        print_info("Point the SeaTalk Bot App callback URL at this webhook endpoint.")

    dm_policy_existing = str(account.get("dm_policy") or "allowlist").lower()
    dm_policy_index = {"allowlist": 0, "open": 1}.get(dm_policy_existing, 0)
    dm_policy_choice = prompt_choice(
        "DM policy",
        ["allowlist", "open"],
        dm_policy_index,
    )
    account["dm_policy"] = ["allowlist", "open"][dm_policy_choice]

    allowed = prompt(
        "DM allowed users, comma-separated emails or employee codes",
        default=_coerce_csv(account.get("allow_from")),
    )
    _set_optional_csv(account, "allow_from", allowed)

    group_policy_existing = str(account.get("group_policy") or "disabled").lower()
    group_policy_index = {"disabled": 0, "allowlist": 1, "open": 2}.get(group_policy_existing, 0)
    group_policy_choice = prompt_choice(
        "Group policy",
        ["disabled", "allowlist", "open"],
        group_policy_index,
    )
    group_policy = ["disabled", "allowlist", "open"][group_policy_choice]
    account["group_policy"] = group_policy
    if group_policy == "allowlist":
        groups = prompt(
            "Allowed groups, comma-separated group ids",
            default=_coerce_csv(account.get("group_allow_from")),
        )
        _set_optional_csv(account, "group_allow_from", groups)
    else:
        account.pop("group_allow_from", None)

    if group_policy in {"allowlist", "open"}:
        group_senders = prompt(
            "Group sender allowlist, comma-separated emails or employee codes (optional)",
            default=_coerce_csv(account.get("group_sender_allow_from")),
        )
        _set_optional_csv(account, "group_sender_allow_from", group_senders)
    else:
        account.pop("group_sender_allow_from", None)

    processing_indicator_existing = str(account.get("processing_indicator") or "typing").lower()
    processing_indicator_index = 1 if processing_indicator_existing == "off" else 0
    processing_indicator_choice = prompt_choice(
        "Processing indicator",
        ["typing", "off"],
        processing_indicator_index,
    )
    account["processing_indicator"] = "off" if processing_indicator_choice == 1 else "typing"

    home_channel = prompt(
        "SeaTalk home channel target (optional)",
        default=str(get_env_value("SEATALK_HOME_CHANNEL") or ""),
    )
    home_channel_thread_id = prompt(
        "SeaTalk home channel thread id (optional)",
        default=str(get_env_value("SEATALK_HOME_CHANNEL_THREAD_ID") or ""),
    )
    home_channel_name = prompt(
        "SeaTalk home channel display name",
        default=str(get_env_value("SEATALK_HOME_CHANNEL_NAME") or "SeaTalk Home"),
    )
    for key, value in (
        ("SEATALK_HOME_CHANNEL", home_channel.strip()),
        ("SEATALK_HOME_CHANNEL_THREAD_ID", home_channel_thread_id.strip()),
        ("SEATALK_HOME_CHANNEL_NAME", home_channel_name.strip()),
    ):
        save_env_value(key, value)
        os.environ[key] = value

    save_config(raw_config)
    print_success("SeaTalk account configuration saved to ~/.hermes/config.yaml")
    print_success("SeaTalk home channel configuration saved to ~/.hermes/.env")
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

    home_envs = getattr(scheduler, "_HOME_TARGET_ENV_VARS", None)
    if isinstance(home_envs, dict):
        home_envs[SEATALK_PLATFORM] = "SEATALK_HOME_CHANNEL"


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
                target = parse_seatalk_target(
                    target_ref,
                    known_accounts=_known_account_ids_from_extra(_config_file_extra()),
                )
            except ValueError:
                return None, None, False
            return _account_qualified_target(target.account_id, target.chat_id), target.thread_id, True
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

    async def _patched_send_to_platform(platform, pconfig, chat_id, message, thread_id=None, media_files=None, **kwargs):
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
            **kwargs,
        )

    _patched_send_to_platform._seatalk_patched = True  # type: ignore[attr-defined]
    _patched_send_to_platform._seatalk_original = original  # type: ignore[attr-defined]
    send_message_tool._send_to_platform = _patched_send_to_platform


async def _run_on_gateway_loop(runner: Any, make_coro: Any) -> Any:
    gateway_loop = getattr(runner, "_gateway_loop", None)
    current_loop = asyncio.get_running_loop()
    if (
        gateway_loop is not None
        and gateway_loop.is_running()
        and gateway_loop is not current_loop
    ):
        future = asyncio.run_coroutine_threadsafe(make_coro(), gateway_loop)
        return await asyncio.wrap_future(future)
    return await make_coro()


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

    metadata: dict[str, Any] = {"_skip_coalescing": True}
    if thread_id:
        metadata["thread_id"] = thread_id
    results: list[Any] = []
    if message:
        entry = platform_registry.get(SEATALK_PLATFORM)
        max_len = entry.max_message_length if entry and entry.max_message_length else MAX_MESSAGE_LENGTH
        for chunk in BasePlatformAdapter.truncate_message(message, max_len):
            result = await _run_on_gateway_loop(
                runner,
                lambda chunk=chunk: runtime_adapter.send(
                    chat_id=chat_id,
                    content=chunk,
                    metadata=metadata,
                ),
            )
            if not getattr(result, "success", False):
                return {"error": f"SeaTalk send failed: {getattr(result, 'error', 'unknown')}"}
            results.append(result)

    for media_path, _is_voice in media_files or []:
        ext = Path(media_path).suffix.lower()
        if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            result = await _run_on_gateway_loop(
                runner,
                lambda media_path=media_path: runtime_adapter.send_image_file(
                    chat_id,
                    media_path,
                    caption="",
                    metadata=metadata,
                ),
            )
        else:
            result = await _run_on_gateway_loop(
                runner,
                lambda media_path=media_path: runtime_adapter.send_document(
                    chat_id,
                    media_path,
                    caption="",
                    metadata=metadata,
                ),
            )
        if not getattr(result, "success", False):
            return {"error": f"SeaTalk media send failed: {getattr(result, 'error', 'unknown')}"}
        results.append(result)

    message_id = getattr(results[-1], "message_id", None) if results else None
    return {"success": True, "message_id": message_id}


def _patch_home_channel() -> None:
    """Read SeaTalk home channel values from Hermes' standard env contract."""
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
        return _make_home_channel(
            HomeChannel,
            platform=platform,
            chat_id=home,
            name=os.getenv("SEATALK_HOME_CHANNEL_NAME", "SeaTalk Home"),
            thread_id=os.getenv("SEATALK_HOME_CHANNEL_THREAD_ID", "").strip() or None,
        )

    _patched_get_home_channel._seatalk_patched = True  # type: ignore[attr-defined]
    _patched_get_home_channel._seatalk_original = original  # type: ignore[attr-defined]
    GatewayConfig.get_home_channel = _patched_get_home_channel


def _make_home_channel(home_channel_cls: Any, *, platform: Any, chat_id: str, name: str, thread_id: str | None) -> Any:
    kwargs = {"platform": platform, "chat_id": chat_id, "name": name}
    try:
        if "thread_id" in inspect.signature(home_channel_cls).parameters:
            kwargs["thread_id"] = thread_id
    except (TypeError, ValueError):
        pass
    return home_channel_cls(**kwargs)


def _platform_value(platform: Any) -> str:
    return str(getattr(platform, "value", platform)).lower()


_OUTBOUND_FETCH_TIMEOUT_SECONDS = 30


def _is_seatalk_hosted_url(url: str) -> bool:
    """Match openclaw fetchRemoteMedia behavior: only SeaTalk-hosted URLs use the
    authenticated download_media path; other URLs are fetched without Bearer."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return False
    return host == "openapi.seatalk.io" or host.endswith(".seatalk.io")


async def _fetch_outbound_media_bytes(client: Any, url: str) -> bytes:
    """Fetch bytes for an outbound media URL.

    SeaTalk-hosted URLs go through the authenticated client (Bearer token);
    other URLs are fetched without Authorization, matching openclaw
    fetchRemoteMedia ([media.ts:136-151]). Local paths should not reach this
    helper — callers use prepare_outbound_media for those.
    """
    if _is_seatalk_hosted_url(url):
        data, _content_type = await client.download_media(url)
        return data
    timeout = aiohttp.ClientTimeout(total=_OUTBOUND_FETCH_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status < 200 or response.status >= 300:
                raise ValueError(
                    f"Failed to fetch media from {url}: HTTP {response.status}"
                )
            return await response.read()


def register(ctx: Any) -> None:
    """Plugin entry point called by the Hermes plugin loader."""
    os.environ[INTERNAL_ALLOW_ALL_ENV] = "true"
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
        install_hint="Install aiohttp>=3.9 and configure SeaTalk accounts in config.yaml.",
        setup_fn=_seatalk_setup_wizard,
        allow_all_env=INTERNAL_ALLOW_ALL_ENV,
        max_message_length=4000,
        emoji="💬",
        platform_hint=_SEATALK_PLATFORM_HINT,
    )
    register_seatalk_tool(ctx)
    setattr(ctx, "_seatalk_platform_registered", True)
