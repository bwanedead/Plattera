"""Loop-agnostic event bus for Agent Viewer SSE streams."""

from __future__ import annotations

import asyncio
import json
import logging
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
        subscriber_count = 0
        with self._lock:
            self._subscribers[stream_key].append((loop, q))
            subscriber_count = len(self._subscribers.get(stream_key, []))
            history_items = list(self._history.get(stream_key, ()))
        if stream_key.startswith("transcript_edit:"):
            logger.info(
                "AGENT_VIEWER_TIMING ► bus_subscribe stream_key=%s history_count=%s subscribers=%s",
                stream_key,
                len(history_items),
                subscriber_count,
            )
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
        should_log = False
        phase = ""
        event_type = ""
        if stream_key.startswith("transcript_edit:") and isinstance(event, dict):
            event_type = str(event.get("event_type") or "")
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            phase = str(payload.get("phase") or "")
            should_log = event_type in {"done", "human_feedback_needed", "human_feedback"} or phase in {
                "starting",
                "orient",
                "audit",
                "audit_result",
                "human_feedback_needed",
                "investigate",
            }
        if should_log:
            logger.info(
                "AGENT_VIEWER_TIMING ► bus_publish stream_key=%s event_type=%s phase=%s seq=%s",
                stream_key,
                event_type or "status",
                phase or "n/a",
                str(event.get("seq") if isinstance(event, dict) else "n/a"),
            )
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
logger = logging.getLogger(__name__)
