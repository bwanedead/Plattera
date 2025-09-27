from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio
from typing import AsyncGenerator
from services.dossier.event_bus import event_bus


router = APIRouter()


async def _sse_stream(q: asyncio.Queue) -> AsyncGenerator[str, None]:
    try:
        while True:
            data = await q.get()
            yield f"data: {data}\n\n"
    except asyncio.CancelledError:
        return


@router.get("/events", include_in_schema=False)
async def dossier_events():
    q = await event_bus.subscribe()
    async def gen():
        try:
            async for chunk in _sse_stream(q):
                yield chunk
        finally:
            await event_bus.unsubscribe(q)
    return StreamingResponse(gen(), media_type="text/event-stream")


