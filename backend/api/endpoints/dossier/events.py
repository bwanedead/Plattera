from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio
import logging
from typing import AsyncGenerator
from services.dossier.event_bus import event_bus
from services.dossier.delete_job_manager import delete_job_manager


router = APIRouter()
logger = logging.getLogger(__name__)


async def _sse_stream(q: asyncio.Queue) -> AsyncGenerator[str, None]:
    try:
        while True:
            try:
                # Wait up to 10 seconds for an event; emit heartbeat if idle
                data = await asyncio.wait_for(q.get(), timeout=10.0)
                yield f"data: {data}\n\n"
            except asyncio.TimeoutError:
                # Heartbeat keeps proxies/browsers from closing the stream
                yield "event: ping\ndata: {}\n\n"
    except asyncio.CancelledError:
        return


@router.get("/events", include_in_schema=False)
async def dossier_events():
    q = await event_bus.subscribe()
    logger.debug(f"SSE: client subscribed, subscribers={event_bus.get_subscriber_count()}")
    async def gen():
        try:
            async for chunk in _sse_stream(q):
                yield chunk
        finally:
            await event_bus.unsubscribe(q)
            logger.debug(f"SSE: client unsubscribed, subscribers={event_bus.get_subscriber_count()}")
    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/bulk/progress/{job_id}", include_in_schema=False)
async def bulk_progress(job_id: str):
    q = await delete_job_manager.subscribe(job_id)
    if not q:
        return StreamingResponse(iter(["event: error\ndata: {\"detail\":\"job not found\"}\n\n"]), media_type="text/event-stream")
    logger.debug(f"SSE: bulk subscribed job={job_id}")
    async def gen():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=10.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            logger.debug(f"SSE: bulk unsubscribed job={job_id}")
    return StreamingResponse(gen(), media_type="text/event-stream")

