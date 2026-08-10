"""Outbound text coalescing for SeaTalk sends."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


SendFn = Callable[[str], Awaitable[None]]
ChunkFn = Callable[[str, int], list[str]]


class OutboundCoalescer:
    def __init__(
        self,
        *,
        send: SendFn,
        chunk_text: ChunkFn,
        max_length: int,
        joiner: str = "\n\n",
        idle_flush_seconds: float = 1.0,
    ):
        self._send = send
        self._chunk_text = chunk_text
        self._max_length = max_length
        self._joiner = joiner
        self._idle_flush_seconds = idle_flush_seconds
        self._buffer = ""
        self._idle_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()

    @property
    def has_buffered(self) -> bool:
        return bool(self._buffer)

    def append(self, text: str) -> None:
        if not text:
            return
        self._cancel_idle_task()
        if not self._buffer:
            self._buffer = text
            self._schedule_idle_flush()
            return

        next_text = f"{self._buffer}{self._joiner}{text}"
        if len(next_text) > self._max_length:
            self.flush_later()
            self._buffer = text
            self._schedule_idle_flush()
            return

        self._buffer = next_text
        self._schedule_idle_flush()

    def flush_later(self) -> None:
        if not self._buffer:
            return
        text = self._consume_buffer()
        task = asyncio.create_task(self._deliver(text, reason="overflow"))
        task.add_done_callback(
            lambda t: logger.warning("SeaTalk coalescer send failed: %s", t.exception())
            if not t.cancelled() and t.exception()
            else None
        )

    async def flush(self) -> None:
        self._cancel_idle_task()
        if not self._buffer:
            return
        await self._deliver(self._consume_buffer(), reason="flush")

    def _consume_buffer(self) -> str:
        text = self._buffer
        self._buffer = ""
        return text

    def _requeue(self, text: str) -> None:
        """Put un-sent text back at the head of the buffer.

        The buffer is consumed *before* the send is awaited, so a failure or a
        cancellation mid-send would otherwise drop the text with no trace.
        """
        if not text:
            return
        self._buffer = f"{text}{self._joiner}{self._buffer}" if self._buffer else text

    async def _deliver(self, text: str, *, reason: str) -> None:
        """Send ``text``, keeping it recoverable if the send does not complete.

        A cancellation here is not benign: ``append`` cancels the pending idle
        task on every new message, and that task may already be inside the
        send. Re-queue the text and log it, so an interrupted send is visible
        and retried on the next flush instead of vanishing silently.
        """
        try:
            await self._send_text(text)
        except asyncio.CancelledError:
            self._requeue(text)
            logger.warning(
                "SeaTalk coalescer send cancelled mid-flight (reason=%s, %d chars); "
                "text re-queued for the next flush",
                reason,
                len(text),
            )
            raise
        except Exception:
            self._requeue(text)
            logger.exception(
                "SeaTalk coalescer send failed (reason=%s, %d chars); text re-queued",
                reason,
                len(text),
            )
            raise

    async def _send_text(self, text: str) -> None:
        async with self._send_lock:
            chunks = self._chunk_text(text, self._max_length)
            for chunk in chunks:
                await self._send(chunk)

    def _schedule_idle_flush(self) -> None:
        if self._idle_flush_seconds <= 0:
            return
        self._idle_task = asyncio.create_task(self._idle_flush())

    async def _idle_flush(self) -> None:
        try:
            await asyncio.sleep(self._idle_flush_seconds)
            if self._buffer:
                await self.flush()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Nothing awaits this task, so an escaping exception would only
            # surface as "Task exception was never retrieved" (or not at all,
            # depending on the asyncio handler). Log it here instead.
            logger.exception("SeaTalk coalescer idle flush failed")

    def _cancel_idle_task(self) -> None:
        task = self._idle_task
        self._idle_task = None
        if task is None or task.done():
            return
        task.cancel()


class OutboundCoalescerMap:
    def __init__(
        self,
        *,
        send_factory: Callable[[str, str | None], SendFn],
        chunk_text: ChunkFn,
        max_length: int,
        idle_flush_seconds: float = 1.0,
    ):
        self._send_factory = send_factory
        self._chunk_text = chunk_text
        self._max_length = max_length
        self._idle_flush_seconds = idle_flush_seconds
        self._items: dict[tuple[str, str | None], OutboundCoalescer] = {}

    def append(self, chat_id: str, thread_id: str | None, text: str) -> None:
        key = (chat_id, thread_id)
        coalescer = self._items.get(key)
        if coalescer is None:
            coalescer = OutboundCoalescer(
                send=self._send_factory(chat_id, thread_id),
                chunk_text=self._chunk_text,
                max_length=self._max_length,
                idle_flush_seconds=self._idle_flush_seconds,
            )
            self._items[key] = coalescer
        coalescer.append(text)

    async def flush_all(self) -> None:
        for key, coalescer in list(self._items.items()):
            await coalescer.flush()
            if not coalescer.has_buffered:
                self._items.pop(key, None)

