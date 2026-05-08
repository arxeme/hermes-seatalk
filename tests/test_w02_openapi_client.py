from __future__ import annotations

import logging
from pathlib import Path

import aiohttp
import pytest

from hermes_seatalk.client import (
    SeaTalkAuthError,
    SeaTalkNetworkError,
    SeaTalkOpenAPIClient,
    SeaTalkProtocolError,
    SeaTalkRateLimitError,
    SeaTalkTargetNotFoundError,
    SeaTalkTokenInfo,
    build_file_message,
    build_image_message,
    build_text_message,
    prepare_outbound_media,
)


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None, raw=b""):
        self.status = status
        self.payload = payload if payload is not None else {"code": 0}
        self.headers = headers or {}
        self.raw = raw

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

    async def read(self):
        return self.raw


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self):
        self.closed = True


async def _noop_sleep(_delay):
    return None


def _client(session, **kwargs):
    return SeaTalkOpenAPIClient(
        "app-id",
        "app-secret",
        base_url="https://mock.seatalk",
        session=session,
        rate_limit_retry_delays=(0.0,),
        sleep_fn=_noop_sleep,
        now_fn=lambda: 1_000,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_t02_01_token_fetch_success_is_cached():
    session = FakeSession([
        FakeResponse(payload={"code": 0, "app_access_token": "token-1", "expire": 10_000}),
    ])
    client = _client(session)

    assert await client.get_access_token() == "token-1"
    assert await client.get_access_token() == "token-1"

    assert len(session.requests) == 1
    request = session.requests[0]
    assert request["method"] == "POST"
    assert request["url"] == "https://mock.seatalk/auth/app_access_token"
    assert request["json"] == {"app_id": "app-id", "app_secret": "app-secret"}


@pytest.mark.asyncio
async def test_t02_02_token_refresh_failure_keeps_old_state():
    session = FakeSession([
        FakeResponse(payload={"code": 999, "message": "bad credential"}),
    ])
    client = _client(session)
    client._token_info = SeaTalkTokenInfo(token="old-token", expire_at=1_500)

    with pytest.raises(SeaTalkAuthError):
        await client.get_access_token()

    assert client._token_info == SeaTalkTokenInfo(token="old-token", expire_at=1_500)


@pytest.mark.asyncio
async def test_t02_03_send_text_payload_target_and_headers():
    session = FakeSession([
        FakeResponse(payload={"code": 0, "app_access_token": "token-1", "expire": 10_000}),
        FakeResponse(payload={"code": 0, "message_id": "m-1"}, headers={"x-rid": "rid-1"}),
    ])
    client = _client(session)

    data = await client.send_single_chat("EmpABC", build_text_message("hello"), "ThreadXYZ")

    assert data["message_id"] == "m-1"
    request = session.requests[1]
    assert request["method"] == "POST"
    assert request["url"] == "https://mock.seatalk/messaging/v2/single_chat"
    assert request["headers"]["Authorization"] == "Bearer token-1"
    assert request["json"] == {
        "employee_code": "EmpABC",
        "message": {
            "tag": "text",
            "text": {"format": 1, "content": "hello"},
            "thread_id": "ThreadXYZ",
        },
    }


@pytest.mark.asyncio
async def test_t02_04_native_media_payloads(tmp_path: Path):
    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"image-bytes")
    file_path = tmp_path / ("a" * 120 + ".txt")
    file_path.write_bytes(b"file-bytes")

    image = prepare_outbound_media(image_path)
    document = prepare_outbound_media(file_path)

    assert image.send_as == "image"
    assert build_image_message(image.base64) == {
        "tag": "image",
        "image": {"content": "aW1hZ2UtYnl0ZXM="},
    }
    assert document.send_as == "file"
    assert len(document.filename) == 100
    assert build_file_message(document.base64, document.filename) == {
        "tag": "file",
        "file": {
            "content": "ZmlsZS1ieXRlcw==",
            "filename": "a" * 100,
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("responses", "expected_error"),
    [
        (
            [
                FakeResponse(payload={"code": 0, "app_access_token": "token-1", "expire": 10_000}),
                FakeResponse(payload={"code": 101, "message": "too many"}),
                FakeResponse(payload={"code": 101, "message": "too many"}),
            ],
            SeaTalkRateLimitError,
        ),
        (
            [
                FakeResponse(payload={"code": 0, "app_access_token": "token-1", "expire": 10_000}),
                FakeResponse(status=401, payload={"code": 0}),
            ],
            SeaTalkAuthError,
        ),
        (
            [
                FakeResponse(payload={"code": 0, "app_access_token": "token-1", "expire": 10_000}),
                FakeResponse(payload={"code": 404, "message": "employee not found"}),
            ],
            SeaTalkTargetNotFoundError,
        ),
        (
            [
                FakeResponse(payload={"code": 0, "app_access_token": "token-1", "expire": 10_000}),
                aiohttp.ClientError("connection failed"),
            ],
            SeaTalkNetworkError,
        ),
        (
            [
                FakeResponse(payload={"code": 0, "app_access_token": "token-1", "expire": 10_000}),
                FakeResponse(payload={"code": 999, "message": "unexpected"}),
            ],
            SeaTalkProtocolError,
        ),
    ],
)
async def test_t02_05_error_mapping(responses, expected_error):
    client = _client(FakeSession(responses))

    with pytest.raises(expected_error):
        await client.send_single_chat("EmpABC", build_text_message("hello"))


@pytest.mark.asyncio
async def test_t02_06_logs_redact_secrets(caplog):
    session = FakeSession([
        FakeResponse(payload={"code": 0, "app_access_token": "token-1", "expire": 10_000}),
        aiohttp.ClientError("failed token-1 app-secret signing-secret"),
    ])
    client = _client(session, log_secrets=["signing-secret"])

    with caplog.at_level(logging.WARNING):
        with pytest.raises(SeaTalkNetworkError):
            await client.send_single_chat("EmpABC", build_text_message("hello"))

    assert "token-1" not in caplog.text
    assert "app-secret" not in caplog.text
    assert "signing-secret" not in caplog.text
    assert "***" in caplog.text


@pytest.mark.asyncio
async def test_t02_07_email_lookup_uses_active_employee_and_cache():
    session = FakeSession([
        FakeResponse(payload={"code": 0, "app_access_token": "token-1", "expire": 10_000}),
        FakeResponse(payload={
            "code": 0,
            "employees": [
                {
                    "email": "Alice@Example.com",
                    "employee_code": "EmpABC",
                    "employee_status": 2,
                },
                {
                    "email": "bob@example.com",
                    "employee_code": "EmpInactive",
                    "employee_status": 1,
                },
            ],
        }),
    ])
    client = _client(session)

    result = await client.get_employee_code_by_email(["ALICE@example.com", "bob@example.com"])
    cached = await client.get_employee_code_by_email(["alice@example.com", "bob@example.com"])

    assert result == {"alice@example.com": "EmpABC", "bob@example.com": None}
    assert cached == {"alice@example.com": "EmpABC", "bob@example.com": None}
    assert len(session.requests) == 2


@pytest.mark.asyncio
async def test_t02_08_remember_employee_email_seeds_lookup_cache():
    client = _client(FakeSession([]))

    client.remember_employee_email("Alice@Example.com", "EmpABC")
    result = await client.get_employee_code_by_email(["alice@example.com"])

    assert result == {"alice@example.com": "EmpABC"}
