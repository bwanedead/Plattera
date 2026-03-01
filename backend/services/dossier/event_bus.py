import asyncio
import json
from typing import Dict, Any, List


class DossierEventBus:
    """
    Simple in-process pub/sub bus for dossier change notifications.
    Backed by per-subscriber asyncio queues; used by SSE endpoint.
    """

    def __init__(self) -> None:
        self._subscribers: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    async def publish(self, event: Dict[str, Any]) -> None:
        data = json.dumps(event)
        async with self._lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(data)
                except Exception:
                    # If a queue is full/broken, drop it
                    try:
                        self._subscribers.remove(q)
                    except Exception:
                        pass

    def publish_best_effort(self, event: Dict[str, Any]) -> None:
        """
        Publish from either async or sync contexts without leaking un-awaited coroutines.

        If called inside an active event loop, schedule a background task.
        Otherwise, run publish synchronously in a temporary loop.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            asyncio.run(self.publish(event))

    def get_subscriber_count(self) -> int:
        # helper for logging purposes only
        return len(self._subscribers)


# Global singleton
event_bus = DossierEventBus()


