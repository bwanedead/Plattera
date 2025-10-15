import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Any

from starlette.concurrency import run_in_threadpool

from .management_service import DossierManagementService
from .event_bus import event_bus
import json


logger = logging.getLogger(__name__)


class DeleteJob:
    def __init__(self, job_id: str, dossier_ids: List[str], max_workers: int = 4) -> None:
        self.job_id = job_id
        self.dossier_ids = list(dict.fromkeys(dossier_ids))  # de-dup preserve order
        self.total = len(self.dossier_ids)
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

        self.done_ids: List[str] = []
        self.failed: List[Dict[str, Any]] = []
        self.in_progress: List[str] = []

        self._queue: asyncio.Queue = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(max_workers)
        self._cancel = asyncio.Event()

    def to_status(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "total": self.total,
            "done": len(self.done_ids),
            "deletedIds": list(self.done_ids),
            "failedIds": [f.get("id") for f in self.failed],
            "inProgressIds": list(self.in_progress),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def get_queue(self) -> asyncio.Queue:
        return self._queue

    def cancel(self) -> None:
        self._cancel.set()


class DeleteJobManager:
    def __init__(self, max_workers: int = 4) -> None:
        self._jobs: Dict[str, DeleteJob] = {}
        self._lock = asyncio.Lock()
        self._max_workers = max_workers
        self._svc = DossierManagementService()

    async def create_job(self, dossier_ids: List[str]) -> DeleteJob:
        job_id = str(uuid.uuid4())
        async with self._lock:
            job = DeleteJob(job_id, dossier_ids, self._max_workers)
            self._jobs[job_id] = job
        logger.info(f"BULK_JOB_START job={job_id} total={job.total} ids={min(job.total, 10)} shown")
        return job

    async def get_job(self, job_id: str) -> Optional[DeleteJob]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def start_job(self, job_id: str) -> None:
        job = await self.get_job(job_id)
        if not job:
            return

        job.started_at = time.time()

        async def purge_one(dossier_id: str):
            if job._cancel.is_set():
                return
            t0 = time.monotonic()
            async with job._semaphore:
                try:
                    job.in_progress.append(dossier_id)
                    logger.info(f"BULK_PURGE_START job={job.job_id} dossier={dossier_id}")
                    ok = await run_in_threadpool(self._svc.delete_dossier, dossier_id, True)
                    dt = int((time.monotonic() - t0) * 1000)
                    try:
                        job.in_progress.remove(dossier_id)
                    except Exception:
                        pass
                    if ok:
                        job.done_ids.append(dossier_id)
                        logger.info(f"BULK_PURGE_DONE job={job.job_id} dossier={dossier_id} ms={dt}")
                        # Push job-scoped SSE event
                        await job._queue.put(
                            f'{{"type":"dossier:deleted","job_id":"{job.job_id}","dossier_id":"{dossier_id}","ms":{dt}}}'
                        )
                        # Also publish global event for existing listeners
                        try:
                            await event_bus.publish({
                                "type": "dossier:deleted",
                                "dossier_id": str(dossier_id)
                            })
                        except Exception:
                            pass
                    else:
                        job.failed.append({"id": dossier_id, "error": "not_found", "ms": dt})
                        logger.warning(f"BULK_PURGE_ERROR job={job.job_id} dossier={dossier_id} ms={dt} error=not_found")
                except Exception as e:
                    dt = int((time.monotonic() - t0) * 1000)
                    try:
                        job.in_progress.remove(dossier_id)
                    except Exception:
                        pass
                    job.failed.append({"id": dossier_id, "error": str(e), "ms": dt})
                    logger.error(f"BULK_PURGE_ERROR job={job.job_id} dossier={dossier_id} ms={dt} error={e}")

        async def runner():
            # Emit start event
            await job._queue.put(
                f'{{"type":"bulk:start","job_id":"{job.job_id}","total":{job.total}}}'
            )
            # Launch tasks
            tasks = [asyncio.create_task(purge_one(did)) for did in job.dossier_ids]
            await asyncio.gather(*tasks)
            job.finished_at = time.time()
            summary = {
                "type": "bulk:done",
                "job_id": job.job_id,
                "deleted": len(job.done_ids),
                "failed": len(job.failed),
                "duration_ms": int((job.finished_at - (job.started_at or job.finished_at)) * 1000),
            }
            await job._queue.put(json.dumps(summary))
            logger.info(
                f"BULK_JOB_DONE job={job.job_id} deleted={len(job.done_ids)} failed={len(job.failed)} duration_ms={summary['duration_ms']}"
            )

        # Start background runner
        asyncio.create_task(runner())

    async def subscribe(self, job_id: str) -> Optional[asyncio.Queue]:
        job = await self.get_job(job_id)
        return job.get_queue() if job else None

    async def status(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = await self.get_job(job_id)
        return job.to_status() if job else None


# Global singleton
delete_job_manager = DeleteJobManager()


