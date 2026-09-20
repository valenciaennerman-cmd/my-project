"""Tiny in-process pub/sub for the SSE stream."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

QUEUE_SIZE = 64


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: str, data: Any) -> None:
        """Fan out to every listener. A slow listener drops events, not blocks."""
        payload = f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("SSE kuyrugu dolu, olay dusuruldu (%s)", event)

    async def stream(self, queue: asyncio.Queue[str]) -> AsyncIterator[str]:
        """Yield SSE frames, with a keep-alive so proxies do not time out."""
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            self.unsubscribe(queue)
