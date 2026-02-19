"""Run-scoped event bus for agent-loop SSE streams."""

from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict
from typing import Any, Dict, List


class AgentLoopEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, List[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = defaultdict(list)
        self._lock = threading.Lock()

    async def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers[run_id].append((loop, q))
        return q

    async def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            queues = self._subscribers.get(run_id, [])
            queues = [(loop, existing) for (loop, existing) in queues if existing is not q]
            if not queues and run_id in self._subscribers:
                del self._subscribers[run_id]
            elif queues:
                self._subscribers[run_id] = queues

    async def publish(self, run_id: str, event: Dict[str, Any]) -> None:
        self.publish_sync(run_id, event)

    def publish_sync(self, run_id: str, event: Dict[str, Any]) -> None:
        data = json.dumps(event)
        with self._lock:
            targets = list(self._subscribers.get(run_id, []))
        for loop, q in targets:
            try:
                loop.call_soon_threadsafe(_safe_put_nowait, q, data)
            except Exception:
                with self._lock:
                    current = self._subscribers.get(run_id, [])
                    self._subscribers[run_id] = [
                        (existing_loop, existing_q)
                        for (existing_loop, existing_q) in current
                        if existing_q is not q
                    ]


def _safe_put_nowait(q: asyncio.Queue, data: str) -> None:
    try:
        q.put_nowait(data)
    except Exception:
        pass


event_bus = AgentLoopEventBus()
