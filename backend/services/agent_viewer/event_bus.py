"""Loop-agnostic event bus for Agent Viewer SSE streams."""

from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict
from collections import deque
from typing import Any


class AgentViewerEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = defaultdict(list)
        self._history: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=300))
        self._lock = threading.Lock()

    async def subscribe(self, stream_key: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        history_items: list[str]
        with self._lock:
            self._subscribers[stream_key].append((loop, q))
            history_items = list(self._history.get(stream_key, ()))
        for data in history_items:
            try:
                q.put_nowait(data)
            except Exception:
                break
        return q

    async def unsubscribe(self, stream_key: str, q: asyncio.Queue) -> None:
        with self._lock:
            current = self._subscribers.get(stream_key, [])
            remaining = [(loop, existing) for (loop, existing) in current if existing is not q]
            if not remaining and stream_key in self._subscribers:
                del self._subscribers[stream_key]
            elif remaining:
                self._subscribers[stream_key] = remaining

    async def publish(self, stream_key: str, event: dict[str, Any]) -> None:
        self.publish_sync(stream_key, event)

    def publish_sync(self, stream_key: str, event: dict[str, Any]) -> None:
        data = json.dumps(event)
        with self._lock:
            self._history[stream_key].append(data)
            targets = list(self._subscribers.get(stream_key, []))
        for loop, q in targets:
            try:
                loop.call_soon_threadsafe(_safe_put_nowait, q, data)
            except Exception:
                with self._lock:
                    current = self._subscribers.get(stream_key, [])
                    self._subscribers[stream_key] = [
                        (existing_loop, existing_q)
                        for (existing_loop, existing_q) in current
                        if existing_q is not q
                    ]


def _safe_put_nowait(q: asyncio.Queue, data: str) -> None:
    try:
        q.put_nowait(data)
    except Exception:
        pass


event_bus = AgentViewerEventBus()
