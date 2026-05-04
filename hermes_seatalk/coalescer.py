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
        task = asyncio.create_task(self._send_text(text))
        task.add_done_callback(
            lambda t: logger.warning("SeaTalk coalescer send failed: %s", t.exception())
            if not t.cancelled() and t.exception()
            else None
        )

    async def flush(self) -> None:
        self._cancel_idle_task()
        if not self._buffer:
            return
        await self._send_text(self._consume_buffer())

    def _consume_buffer(self) -> str:
        text = self._buffer
        self._buffer = ""
        return text

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

    def _cancel_idle_task(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None


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

