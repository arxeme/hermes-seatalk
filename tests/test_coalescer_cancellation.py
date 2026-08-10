"""Outbound coalescer must not lose text when a send is interrupted.

``OutboundCoalescer.append`` cancels the pending idle-flush task on every new
message. That task may already be inside the send (awaiting the HTTP call or the
send lock), and the buffer is consumed *before* the send is awaited — so a naive
cancel drops the text with no trace. These tests pin the recovery behaviour.
"""

from __future__ import annotations

import asyncio

import pytest

from hermes_seatalk.coalescer import OutboundCoalescer


def _chunk(text: str, limit: int) -> list[str]:
    return [text[i : i + limit] for i in range(0, len(text), limit)] or [""]


@pytest.mark.asyncio
async def test_append_during_inflight_send_does_not_lose_text() -> None:
    """A new message arriving mid-send must not discard the in-flight text."""
    sent: list[str] = []
    release = asyncio.Event()

    async def slow_send(text: str) -> None:
        await release.wait()
        sent.append(text)

    c = OutboundCoalescer(
        send=slow_send, chunk_text=_chunk, max_length=4000, idle_flush_seconds=0.01
    )

    c.append("A")
    # Let the idle task fire and block inside the send.
    await asyncio.sleep(0.05)
    assert sent == [], "send should still be in flight"

    # B arrives while A is mid-send -> append cancels the idle task.
    c.append("B")
    release.set()
    await asyncio.sleep(0.05)

    # A must not have vanished: it is either delivered or back in the buffer.
    delivered = "".join(sent)
    assert "A" in delivered or "A" in c._buffer, (
        f"'A' was lost: sent={sent!r} buffer={c._buffer!r}"
    )


@pytest.mark.asyncio
async def test_failed_send_requeues_text_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    """A failing send must re-queue its text and say so in the log."""
    attempts: list[str] = []

    async def failing_send(text: str) -> None:
        attempts.append(text)
        raise RuntimeError("boom")

    c = OutboundCoalescer(
        send=failing_send, chunk_text=_chunk, max_length=4000, idle_flush_seconds=0.01
    )

    with caplog.at_level("WARNING"):
        c.append("hello")
        await asyncio.sleep(0.05)

    assert attempts, "send should have been attempted"
    assert c._buffer == "hello", "failed text must be re-queued, not dropped"
    assert any("re-queued" in r.message or "re-queued" in r.getMessage() for r in caplog.records), (
        f"expected a re-queue warning, got: {[r.getMessage() for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_idle_flush_failure_is_logged_not_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An exception inside the idle flush must not disappear into the task."""

    async def failing_send(text: str) -> None:
        raise RuntimeError("boom")

    c = OutboundCoalescer(
        send=failing_send, chunk_text=_chunk, max_length=4000, idle_flush_seconds=0.01
    )

    with caplog.at_level("WARNING"):
        c.append("x")
        await asyncio.sleep(0.05)

    assert caplog.records, "idle flush failure must be logged"
