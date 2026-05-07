"""Lightweight credential probe for SeaTalk OpenAPI."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .client import SeaTalkOpenAPIClient


@dataclass(frozen=True)
class SeaTalkProbeResult:
    ok: bool
    app_id: str | None = None
    latency_ms: int | None = None
    error: str | None = None


async def probe_seatalk(
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
) -> SeaTalkProbeResult:
    """Test SeaTalk API credentials by fetching an access token.

    Equivalent to openclaw-seatalk's ``probeSeaTalk``.  Creates a short-lived
    client, fetches a token, measures round-trip latency, then closes the
    session.  Safe to call at any time without affecting runtime state.
    """
    if not app_id or not app_secret:
        return SeaTalkProbeResult(
            ok=False,
            app_id=app_id,
            error="missing credentials (app_id, app_secret)",
        )

    start = time.monotonic()
    async with SeaTalkOpenAPIClient(app_id, app_secret) as client:
        try:
            await client.get_access_token()
            latency_ms = int((time.monotonic() - start) * 1000)
            return SeaTalkProbeResult(ok=True, app_id=app_id, latency_ms=latency_ms)
        except Exception as exc:  # noqa: BLE001
            return SeaTalkProbeResult(ok=False, app_id=app_id, error=str(exc))
