"""SeaTalk OpenAPI client used by the Hermes SeaTalk plugin."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlencode

import aiohttp


BASE_URL = "https://openapi.seatalk.io"
HTTP_TIMEOUT_SECONDS = 10
MEDIA_TIMEOUT_SECONDS = 60
TOKEN_REFRESH_MARGIN_SECONDS = 600
RATE_LIMIT_RETRY_DELAYS_SECONDS = (10.0, 60.0)
EMAIL_BATCH_LIMIT = 500
EMAIL_POSITIVE_TTL_SECONDS = 24 * 60 * 60
EMAIL_NEGATIVE_TTL_SECONDS = 10 * 60
MAX_OUTBOUND_RAW_BYTES = int(3.75 * 1024 * 1024)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeaTalkTokenInfo:
    token: str
    expire_at: int


@dataclass(frozen=True)
class SeaTalkPreparedMedia:
    base64: str
    send_as: str
    filename: str | None = None


class SeaTalkError(Exception):
    """Base exception carrying API diagnostics without secrets."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        http_status: int | None = None,
        x_rid: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.x_rid = x_rid


class SeaTalkAuthError(SeaTalkError):
    pass


class SeaTalkRateLimitError(SeaTalkError):
    pass


class SeaTalkTargetNotFoundError(SeaTalkError):
    pass


class SeaTalkNetworkError(SeaTalkError):
    pass


class SeaTalkProtocolError(SeaTalkError):
    pass


def _now_seconds() -> int:
    return int(time.time())


def redact_for_log(value: Any, secrets: list[str | None]) -> str:
    """Return a log-safe string with known credentials removed."""
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def build_text_message(content: str, fmt: int = 1) -> dict[str, Any]:
    return {"tag": "text", "text": {"format": fmt, "content": content}}


def build_image_message(base64_content: str) -> dict[str, Any]:
    return {"tag": "image", "image": {"content": base64_content}}


def build_file_message(base64_content: str, filename: str) -> dict[str, Any]:
    return {
        "tag": "file",
        "file": {"content": base64_content, "filename": filename or "file"},
    }


def prepare_outbound_media(path: str | Path, file_name: str | None = None) -> SeaTalkPreparedMedia:
    media_path = Path(path)
    raw = media_path.read_bytes()
    return prepare_outbound_media_bytes(raw, file_name or media_path.name or "file")


def prepare_outbound_media_bytes(raw: bytes, file_name: str) -> SeaTalkPreparedMedia:
    if len(raw) > MAX_OUTBOUND_RAW_BYTES:
        mb = len(raw) / 1024 / 1024
        raise ValueError(f"SeaTalk media file too large: {mb:.1f}MB exceeds ~3.75MB")

    detected_name = file_name or "file"
    encoded = base64.b64encode(raw).decode("ascii")
    ext = Path(detected_name).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return SeaTalkPreparedMedia(base64=encoded, send_as="image")
    return SeaTalkPreparedMedia(
        base64=encoded,
        send_as="file",
        filename=detected_name[:100] or "file",
    )


class SeaTalkOpenAPIClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        base_url: str = BASE_URL,
        session: aiohttp.ClientSession | None = None,
        timeout_seconds: float = HTTP_TIMEOUT_SECONDS,
        media_timeout_seconds: float = MEDIA_TIMEOUT_SECONDS,
        token_refresh_margin_seconds: int = TOKEN_REFRESH_MARGIN_SECONDS,
        rate_limit_retry_delays: tuple[float, ...] = RATE_LIMIT_RETRY_DELAYS_SECONDS,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now_fn: Callable[[], int] = _now_seconds,
        log_secrets: list[str] | None = None,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.media_timeout_seconds = media_timeout_seconds
        self.token_refresh_margin_seconds = token_refresh_margin_seconds
        self.rate_limit_retry_delays = rate_limit_retry_delays
        self._sleep = sleep_fn
        self._now = now_fn
        self._log_secrets = log_secrets or []
        self._session = session
        self._owns_session = session is None
        self._token_info: SeaTalkTokenInfo | None = None
        self._token_task: asyncio.Task[SeaTalkTokenInfo] | None = None
        self._email_cache: dict[str, tuple[str | None, int]] = {}

    async def close(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> SeaTalkOpenAPIClient:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    def _secrets(self, access_token: str | None = None) -> list[str | None]:
        return [self.app_secret, access_token, *self._log_secrets]

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def get_access_token(self) -> str:
        if self._token_info is not None:
            remaining = self._token_info.expire_at - self._now()
            if remaining > self.token_refresh_margin_seconds:
                return self._token_info.token
        return (await self.refresh_token()).token

    async def refresh_token(self) -> SeaTalkTokenInfo:
        if self._token_task is not None:
            return await self._token_task

        task = asyncio.create_task(self._fetch_token())
        self._token_task = task
        try:
            info = await task
            self._token_info = info
            return info
        finally:
            if self._token_task is task:
                self._token_task = None

    async def _fetch_token(self) -> SeaTalkTokenInfo:
        data, _, _ = await self._request_json_without_token(
            "POST",
            "/auth/app_access_token",
            json_body={"app_id": self.app_id, "app_secret": self.app_secret},
        )

        code = data.get("code")
        if code != 0:
            message = data.get("message", "unknown")
            raise SeaTalkAuthError(
                f"SeaTalk token error: code={code} message={message}",
                code=code if isinstance(code, int) else None,
            )

        token = data.get("app_access_token")
        expire = data.get("expire")
        if not token or not isinstance(expire, int):
            raise SeaTalkProtocolError("SeaTalk token response missing token or expire")
        return SeaTalkTokenInfo(token=token, expire_at=expire)

    async def api_call(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        *,
        retry_token: bool = True,
        rate_limit_attempt: int = 0,
    ) -> dict[str, Any]:
        token = await self.get_access_token()
        data, x_rid, http_status = await self._request_json_with_token(method, path, token, body)
        code = data.get("code")

        if code == 0:
            return data

        if code == 100 and retry_token:
            await self.refresh_token()
            return await self.api_call(
                method,
                path,
                body,
                retry_token=False,
                rate_limit_attempt=rate_limit_attempt,
            )

        if code == 101:
            if rate_limit_attempt < len(self.rate_limit_retry_delays):
                delay = self.rate_limit_retry_delays[rate_limit_attempt]
                logger.warning(
                    "SeaTalk API rate limited (code=101) on %s %s; retrying in %.0fs (attempt %d/%d)",
                    method,
                    path,
                    delay,
                    rate_limit_attempt + 1,
                    len(self.rate_limit_retry_delays),
                )
                await self._sleep(delay)
                return await self.api_call(
                    method,
                    path,
                    body,
                    retry_token=retry_token,
                    rate_limit_attempt=rate_limit_attempt + 1,
                )
            raise SeaTalkRateLimitError(
                f"SeaTalk rate limit exceeded after {rate_limit_attempt + 1} attempts",
                code=101,
                http_status=http_status,
                x_rid=x_rid,
            )

        raise self._api_error_for_code(data, http_status=http_status, x_rid=x_rid)

    async def _request_json_without_token(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
    ) -> tuple[dict[str, Any], str | None, int]:
        return await self._request_json(
            method,
            path,
            headers={"Content-Type": "application/json"},
            json_body=json_body,
            timeout=self.timeout_seconds,
            secrets=self._secrets(),
        )

    async def _request_json_with_token(
        self,
        method: str,
        path: str,
        token: str,
        json_body: Any | None = None,
    ) -> tuple[dict[str, Any], str | None, int]:
        return await self._request_json(
            method,
            path,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json_body=json_body,
            timeout=self.timeout_seconds,
            secrets=self._secrets(token),
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        json_body: Any | None,
        timeout: float,
        secrets: list[str | None],
    ) -> tuple[dict[str, Any], str | None, int]:
        url = f"{self.base_url}{path}"
        try:
            async with self._get_session().request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=timeout,
            ) as response:
                x_rid = response.headers.get("x-rid")
                http_status = response.status
                if http_status in (401, 403):
                    raise SeaTalkAuthError(
                        f"SeaTalk API auth failed: HTTP {http_status}",
                        http_status=http_status,
                        x_rid=x_rid,
                    )
                if http_status == 404:
                    raise SeaTalkTargetNotFoundError(
                        "SeaTalk API target not found: HTTP 404",
                        http_status=http_status,
                        x_rid=x_rid,
                    )
                if http_status == 429:
                    raise SeaTalkRateLimitError(
                        "SeaTalk API rate limited: HTTP 429",
                        http_status=http_status,
                        x_rid=x_rid,
                    )
                if http_status < 200 or http_status >= 300:
                    raise SeaTalkProtocolError(
                        f"SeaTalk API error: HTTP {http_status}",
                        http_status=http_status,
                        x_rid=x_rid,
                    )
                try:
                    data = await response.json()
                except Exception as exc:  # noqa: BLE001
                    raise SeaTalkProtocolError(
                        "SeaTalk API returned non-JSON response",
                        http_status=http_status,
                        x_rid=x_rid,
                    ) from exc
                if not isinstance(data, dict):
                    raise SeaTalkProtocolError(
                        "SeaTalk API returned invalid JSON payload",
                        http_status=http_status,
                        x_rid=x_rid,
                    )
                return data, x_rid, http_status
        except SeaTalkError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            logger.warning("SeaTalk network error: %s", redact_for_log(exc, secrets))
            raise SeaTalkNetworkError("SeaTalk network error") from exc

    def _api_error_for_code(
        self,
        data: dict[str, Any],
        *,
        http_status: int | None,
        x_rid: str | None,
    ) -> SeaTalkError:
        code = data.get("code")
        message = str(data.get("message", "unknown"))
        kwargs = {
            "code": code if isinstance(code, int) else None,
            "http_status": http_status,
            "x_rid": x_rid,
        }
        lower_message = message.lower()
        if code == 100:
            return SeaTalkAuthError(
                f"SeaTalk API auth failed: code={code} message={message}",
                **kwargs,
            )
        if code == 101:
            return SeaTalkRateLimitError(
                f"SeaTalk API rate limited: code={code} message={message}",
                **kwargs,
            )
        if (
            code in {102, 103, 404}
            or "not found" in lower_message
            or "no active employee" in lower_message
            or "target" in lower_message and "invalid" in lower_message
        ):
            return SeaTalkTargetNotFoundError(
                f"SeaTalk target not found: code={code} message={message}",
                **kwargs,
            )
        return SeaTalkProtocolError(
            f"SeaTalk API error: code={code} message={message}",
            **kwargs,
        )

    async def send_single_chat(
        self,
        employee_code: str,
        message: dict[str, Any],
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        payload_message = {**message, "thread_id": thread_id} if thread_id else message
        return await self.api_call(
            "POST",
            "/messaging/v2/single_chat",
            {"employee_code": employee_code, "message": payload_message},
        )

    async def send_group_chat(
        self,
        group_id: str,
        message: dict[str, Any],
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        payload_message = {**message, "thread_id": thread_id} if thread_id else message
        return await self.api_call(
            "POST",
            "/messaging/v2/group_chat",
            {"group_id": group_id, "message": payload_message},
        )

    async def send_single_text(
        self,
        employee_code: str,
        text: str,
        *,
        fmt: int = 1,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        return await self.send_single_chat(employee_code, build_text_message(text, fmt), thread_id)

    async def send_group_text(
        self,
        group_id: str,
        text: str,
        *,
        fmt: int = 1,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        return await self.send_group_chat(group_id, build_text_message(text, fmt), thread_id)

    async def send_single_chat_typing(
        self,
        employee_code: str,
        thread_id: str | None = None,
    ) -> None:
        body: dict[str, str] = {"employee_code": employee_code}
        if thread_id:
            body["thread_id"] = thread_id
        await self.api_call("POST", "/messaging/v2/single_chat_typing", body)

    async def send_group_chat_typing(self, group_id: str, thread_id: str | None = None) -> None:
        body: dict[str, str] = {"group_id": group_id}
        if thread_id:
            body["thread_id"] = thread_id
        await self.api_call("POST", "/messaging/v2/group_chat_typing", body)

    async def get_employee_code_by_email(self, emails: list[str]) -> dict[str, str | None]:
        result: dict[str, str | None] = {}
        missing: list[str] = []
        now = self._now()

        for email in emails:
            key = email.strip().lower()
            cached = self._email_cache.get(key)
            if cached is not None and cached[1] > now:
                result[key] = cached[0]
            elif key:
                missing.append(key)

        for start in range(0, len(missing), EMAIL_BATCH_LIMIT):
            batch = missing[start : start + EMAIL_BATCH_LIMIT]
            data = await self.api_call(
                "POST",
                "/contacts/v2/get_employee_code_with_email",
                {"emails": batch},
            )
            found: dict[str, str | None] = {email: None for email in batch}
            for employee in data.get("employees", []) or []:
                if not isinstance(employee, dict):
                    continue
                email = str(employee.get("email", "")).strip().lower()
                code = employee.get("employee_code")
                if email in found and code and employee.get("employee_status") == 2:
                    found[email] = str(code)

            for email, code in found.items():
                ttl = EMAIL_POSITIVE_TTL_SECONDS if code else EMAIL_NEGATIVE_TTL_SECONDS
                self._email_cache[email] = (code, now + ttl)
                result[email] = code

        return result

    def remember_employee_email(self, email: str | None, employee_code: str | None) -> None:
        key = (email or "").strip().lower()
        code = (employee_code or "").strip()
        if not key or not code:
            return
        self._email_cache[key] = (code, self._now() + EMAIL_POSITIVE_TTL_SECONDS)

    async def get_group_chat_history(
        self,
        group_id: str,
        *,
        page_size: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params = {"group_id": group_id, "page_size": str(page_size)}
        if cursor:
            params["cursor"] = cursor
        return await self.api_call("GET", f"/messaging/v2/group_chat/history?{urlencode(params)}")

    async def get_joined_group_chats(
        self,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if page_size:
            params["page_size"] = str(page_size)
        if cursor:
            params["cursor"] = cursor
        suffix = f"?{urlencode(params)}" if params else ""
        return await self.api_call("GET", f"/messaging/v2/group_chat/joined{suffix}")

    async def get_group_info(self, group_id: str) -> dict[str, Any]:
        return await self.api_call(
            "GET",
            f"/messaging/v2/group_chat/info?{urlencode({'group_id': group_id})}",
        )

    async def get_dm_thread(
        self,
        employee_code: str,
        thread_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params = {"employee_code": employee_code, "thread_id": thread_id}
        if page_size:
            params["page_size"] = str(page_size)
        if cursor:
            params["cursor"] = cursor
        return await self.api_call(
            "GET",
            f"/messaging/v2/single_chat/get_thread_by_thread_id?{urlencode(params)}",
        )

    async def get_group_thread(
        self,
        group_id: str,
        thread_id: str,
        *,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params = {"group_id": group_id, "thread_id": thread_id}
        if page_size:
            params["page_size"] = str(page_size)
        if cursor:
            params["cursor"] = cursor
        return await self.api_call(
            "GET",
            f"/messaging/v2/group_chat/get_thread_by_thread_id?{urlencode(params)}",
        )

    async def get_message_by_id(self, message_id: str) -> dict[str, Any]:
        return await self.api_call(
            "GET",
            f"/messaging/v2/get_message_by_message_id?{urlencode({'message_id': message_id})}",
        )

    async def download_media(self, url: str) -> tuple[bytes, str]:
        token = await self.get_access_token()
        try:
            async with self._get_session().request(
                "GET",
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.media_timeout_seconds,
            ) as response:
                if response.status < 200 or response.status >= 300:
                    raise SeaTalkProtocolError(
                        f"SeaTalk media download failed: HTTP {response.status}",
                        http_status=response.status,
                        x_rid=response.headers.get("x-rid"),
                    )
                content_type = response.headers.get("content-type", "application/octet-stream")
                return await response.read(), content_type
        except SeaTalkError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            logger.warning("SeaTalk media network error: %s", redact_for_log(exc, self._secrets(token)))
            raise SeaTalkNetworkError("SeaTalk media network error") from exc
