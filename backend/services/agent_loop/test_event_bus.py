from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.services.agent_loop.event_bus import AgentLoopEventBus


def test_event_bus_publish_sync_delivers_to_async_subscriber() -> None:
    async def _run() -> None:
        bus = AgentLoopEventBus()
        queue = await bus.subscribe("run1")
        bus.publish_sync("run1", {"event_type": "hello", "value": 1})
        data = await asyncio.wait_for(queue.get(), timeout=1.0)
        payload = json.loads(data)
        assert payload["event_type"] == "hello"
        await bus.unsubscribe("run1", queue)

    asyncio.run(_run())

