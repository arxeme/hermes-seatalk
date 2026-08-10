"""The idle flush must not cancel itself.

``flush`` cancels the pending idle task before sending, but ``_idle_flush``
calls ``flush``. Without a self-check that cancels the very task performing the
send: CancelledError lands at the first await inside ``_send_text`` and the
request dies mid-flight. Observed in production as "adapter returned success,
nothing arrived" for every coalesced send.
"""

from __future__ import annotations

import asyncio

import pytest

from hermes_seatalk.coalescer import OutboundCoalescer


def _chunk(text: str, limit: int) -> list[str]:
    return [text[i : i + limit] for i in range(0, len(text), limit)] or [""]


@pytest.mark.asyncio
async def test_idle_flush_completes_the_send() -> None:
    """A single queued message must actually be sent by the idle flush."""
    sent: list[str] = []

    async def record(text: str) -> None:
        # Yield at least once: a real HTTP send suspends, which is where a
        # self-inflicted cancellation would surface.
        await asyncio.sleep(0)
        sent.append(text)

    c = OutboundCoalescer(
        send=record, chunk_text=_chunk, max_length=4000, idle_flush_seconds=0.01
    )
    c.append("hello")
    await asyncio.sleep(0.1)

    assert sent == ["hello"], f"idle flush did not deliver: sent={sent!r} buffer={c._buffer!r}"
    assert c._buffer == "", f"buffer should be empty after a successful flush: {c._buffer!r}"


@pytest.mark.asyncio
async def test_idle_flush_survives_a_slow_send() -> None:
    """The send must survive suspension points, not be cancelled at the first one."""
    sent: list[str] = []

    async def slow(text: str) -> None:
        await asyncio.sleep(0.03)
        sent.append(text)

    c = OutboundCoalescer(
        send=slow, chunk_text=_chunk, max_length=4000, idle_flush_seconds=0.01
    )
    c.append("slow-payload")
    await asyncio.sleep(0.15)

    assert sent == ["slow-payload"], f"slow send was aborted: sent={sent!r} buffer={c._buffer!r}"


@pytest.mark.asyncio
async def test_multi_chunk_send_is_not_cut_short() -> None:
    """Every chunk must go out; a cancellation used to truncate after the first."""
    sent: list[str] = []

    async def record(text: str) -> None:
        await asyncio.sleep(0)
        sent.append(text)

    c = OutboundCoalescer(
        send=record, chunk_text=_chunk, max_length=5, idle_flush_seconds=0.01
    )
    c.append("abcdefghij")  # 10 chars -> 2 chunks of 5
    await asyncio.sleep(0.1)

    assert sent == ["abcde", "fghij"], f"chunks lost: {sent!r}"
