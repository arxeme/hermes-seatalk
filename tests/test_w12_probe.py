from __future__ import annotations

import pytest

from hermes_seatalk import SeaTalkProbeResult, probe_seatalk
from hermes_seatalk.client import SeaTalkAuthError, SeaTalkOpenAPIClient


async def _ok_token(self: SeaTalkOpenAPIClient) -> str:
    return "tok-test"


async def _fail_token(self: SeaTalkOpenAPIClient) -> str:
    raise SeaTalkAuthError("SeaTalk token error: code=101 message=invalid credentials", code=101)


@pytest.mark.asyncio
async def test_t12_01_probe_success(monkeypatch):
    closed = []
    original_close = SeaTalkOpenAPIClient.close

    async def _tracking_close(self: SeaTalkOpenAPIClient) -> None:
        closed.append(self.app_id)
        await original_close(self)

    monkeypatch.setattr(SeaTalkOpenAPIClient, "get_access_token", _ok_token)
    monkeypatch.setattr(SeaTalkOpenAPIClient, "close", _tracking_close)

    result = await probe_seatalk(app_id="app-id", app_secret="secret")

    assert result.ok is True
    assert result.app_id == "app-id"
    assert isinstance(result.latency_ms, int)
    assert result.latency_ms >= 0
    assert result.error is None
    assert closed == ["app-id"]


@pytest.mark.asyncio
async def test_t12_02_probe_auth_failure(monkeypatch):
    monkeypatch.setattr(SeaTalkOpenAPIClient, "get_access_token", _fail_token)

    result = await probe_seatalk(app_id="app-id", app_secret="bad-secret")

    assert result.ok is False
    assert result.app_id == "app-id"
    assert result.error is not None
    assert "101" in result.error or "invalid" in result.error.lower()


@pytest.mark.asyncio
async def test_t12_03_probe_missing_credentials():
    assert (await probe_seatalk()).ok is False
    assert (await probe_seatalk(app_id="app-id")).ok is False
    assert (await probe_seatalk(app_secret="secret")).ok is False

    result = await probe_seatalk()
    assert "missing" in result.error.lower()


@pytest.mark.asyncio
async def test_t12_04_probe_unexpected_error(monkeypatch):
    async def _boom(self: SeaTalkOpenAPIClient) -> str:
        raise RuntimeError("network timeout")

    monkeypatch.setattr(SeaTalkOpenAPIClient, "get_access_token", _boom)

    result = await probe_seatalk(app_id="app-id", app_secret="secret")

    assert result.ok is False
    assert "timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_t12_05_probe_closes_client_on_success(monkeypatch):
    closed: list[str] = []
    original_close = SeaTalkOpenAPIClient.close

    async def _tracking_close(self: SeaTalkOpenAPIClient) -> None:
        closed.append(self.app_id)
        await original_close(self)

    monkeypatch.setattr(SeaTalkOpenAPIClient, "get_access_token", _ok_token)
    monkeypatch.setattr(SeaTalkOpenAPIClient, "close", _tracking_close)

    await probe_seatalk(app_id="my-app", app_secret="secret")

    assert closed == ["my-app"]


@pytest.mark.asyncio
async def test_t12_06_probe_closes_client_on_failure(monkeypatch):
    closed: list[str] = []
    original_close = SeaTalkOpenAPIClient.close

    async def _tracking_close(self: SeaTalkOpenAPIClient) -> None:
        closed.append(self.app_id)
        await original_close(self)

    monkeypatch.setattr(SeaTalkOpenAPIClient, "get_access_token", _fail_token)
    monkeypatch.setattr(SeaTalkOpenAPIClient, "close", _tracking_close)

    await probe_seatalk(app_id="my-app", app_secret="secret")

    assert closed == ["my-app"]


def test_t12_07_probe_result_is_dataclass():
    r = SeaTalkProbeResult(ok=True, app_id="x", latency_ms=42)
    assert r.ok is True
    assert r.latency_ms == 42
    assert r.error is None
