from __future__ import annotations

import threading
import queue
from datetime import datetime
from typing import Optional, Callable, Dict, Any, List

from .job_store import ImageToTextJobStore
from .job_models import JobStatus
from .processor_adapter import ImageToTextProcessorAdapter


class ImageToTextQueueService:
    """
    Sequential queue (concurrency=1) for Image-to-Text jobs.
    """

    def __init__(
        self,
        store: ImageToTextJobStore,
        processor: ImageToTextProcessorAdapter,
        on_status: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    ) -> None:
        self.store = store
        self.processor = processor
        self.on_status = on_status
        self._q: "queue.Queue[str]" = queue.Queue()
        self._worker_started = False
        self._lock = threading.Lock()

    def enqueue_batch(self, job_ids: List[str]) -> None:
        for jid in job_ids:
            self._q.put(jid)
        self._ensure_worker()

    def enqueue(self, job_id: str) -> None:
        self._q.put(job_id)
        self._ensure_worker()

    def _ensure_worker(self) -> None:
        with self._lock:
            if not self._worker_started:
                t = threading.Thread(target=self._run_loop, daemon=True)
                t.start()
                self._worker_started = True

    def _run_loop(self) -> None:
        while True:
            job_id = self._q.get()
            try:
                self._run_job(job_id)
            except Exception as e:
                # best-effort failure status
                try:
                    self.store.update_status(job_id, JobStatus.FAILED, error=str(e), finished_at=datetime.utcnow().isoformat())
                except Exception:
                    pass
            finally:
                self._q.task_done()

    def _run_job(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if not job:
            return
        # If per-file auto dossier was requested, ensure we capture dynamically created ids from processor
        auto_per_file = bool((job or {}).get('auto_create_dossier_per_file'))
        self.store.update_status(job_id, JobStatus.RUNNING, started_at=datetime.utcnow().isoformat())
        if self.on_status:
            try:
                self.on_status(job_id, JobStatus.RUNNING.value, {})
            except Exception:
                pass

        try:
            result = self.processor.process(job)
            # Persist any dynamically created dossier/transcription ids back to store for later steps
            try:
                dyn_dossier = result.get('metadata', {}).get('dossier_id') if isinstance(result, dict) else None
                dyn_transcription = result.get('metadata', {}).get('transcription_id') if isinstance(result, dict) else None
                if dyn_dossier or dyn_transcription:
                    self.store.update_fields(job_id, dossier_id=dyn_dossier or job.get('dossier_id'), transcription_id=dyn_transcription or job.get('transcription_id'))
            except Exception:
                pass
            if not isinstance(result, dict) or not result.get("success", False):
                err = (result or {}).get("error", "Processing failed") if isinstance(result, dict) else "Processing failed"
                self.store.update_status(job_id, JobStatus.FAILED, error=str(err), finished_at=datetime.utcnow().isoformat())
                if self.on_status:
                    try:
                        self.on_status(job_id, JobStatus.FAILED.value, {"error": str(err)})
                    except Exception:
                        pass
                return

            # Persist result files into dossier structure if context provided (fallback in case progressive saver didn't run)
            try:
                dossier_id = (job or {}).get("dossier_id") if isinstance(job, dict) else None
                transcription_id = (job or {}).get("transcription_id") if isinstance(job, dict) else None
                # If worker created them dynamically, fetch latest
                if not dossier_id:
                    dossier_id = (self.store.get(job_id) or {}).get('dossier_id')
                if not transcription_id:
                    transcription_id = (self.store.get(job_id) or {}).get('transcription_id')
                if dossier_id and transcription_id:
                    from pathlib import Path as _Path
                    import json as _json
                    from datetime import datetime as _dt
                    # Build drafts directory
                    _BACKEND_DIR = _Path(__file__).resolve().parents[2]
                    drafts_dir = _BACKEND_DIR / "dossiers_data" / "views" / "transcriptions" / str(dossier_id) / str(transcription_id) / "raw"
                    drafts_dir.mkdir(parents=True, exist_ok=True)

                    # Compose content from result
                    extracted_text = result.get("extracted_text")
                    content: dict
                    try:
                        if isinstance(extracted_text, str) and extracted_text.strip().startswith('{'):
                            parsed = _json.loads(extracted_text)
                            content = parsed if isinstance(parsed, dict) else {"text": extracted_text}
                        elif isinstance(extracted_text, dict):
                            # If upstream already produced dict, use it directly
                            content = extracted_text
                        else:
                            content = {"text": extracted_text or ""}
                    except Exception:
                        content = {"text": str(extracted_text or "")}

                    # Normalize flags (ensure not placeholder)
                    content.pop('_placeholder', None)
                    content['_status'] = 'completed'
                    content['_draft_index'] = 0
                    content['_created_at'] = content.get('_created_at') or _dt.now().isoformat()

                    # Write v1 and base files
                    v1_path = drafts_dir / f"{transcription_id}_v1.json"
                    base_path = drafts_dir / f"{transcription_id}.json"
                    with open(v1_path, 'w', encoding='utf-8') as vf:
                        _json.dump(content, vf, indent=2, ensure_ascii=False)
                    with open(base_path, 'w', encoding='utf-8') as bf:
                        _json.dump(content, bf, indent=2, ensure_ascii=False)

                    # Mark run metadata as completed for v1
                    try:
                        from services.dossier.management_service import DossierManagementService as _DMS
                        _ms = _DMS()
                        _ms.update_run_metadata(
                            dossier_id=str(dossier_id),
                            transcription_id=str(transcription_id),
                            updates={
                                "completed_drafts": f"{transcription_id}_v1",
                                "status": "completed",
                                "timestamps": {"finished_at": _dt.now().isoformat()},
                            },
                        )
                    except Exception:
                        pass

                    # Create provenance and attach image thumbnails metadata to association for UI
                    try:
                        from api.endpoints.dossier.dossier_utils import create_transcription_provenance
                        from services.dossier.association_service import TranscriptionAssociationService as _TAS
                        model = (job or {}).get('model') if isinstance(job, dict) else None
                        extraction_mode = (job or {}).get('extraction_mode') if isinstance(job, dict) else None
                        enhancement_settings = (job or {}).get('enhancement_settings') if isinstance(job, dict) else None
                        provenance = create_transcription_provenance(
                            file_path=(job or {}).get('source_path'),
                            model=model or "gpt-4o",
                            extraction_mode=extraction_mode or "legal_document_json",
                            result=result if isinstance(result, dict) else {},
                            transcription_id=str(transcription_id),
                            enhancement_settings=enhancement_settings or {},
                            save_images=True,
                        )

                        images_meta = {}
                        try:
                            import os as _os
                            from pathlib import Path as _PURL
                            orig_path = provenance.get("enhancement", {}).get("original_image_path") if isinstance(provenance, dict) else None
                            proc_path = provenance.get("enhancement", {}).get("processed_image_path") if isinstance(provenance, dict) else None
                            if orig_path:
                                filename = _PURL(orig_path).name
                                images_meta["original_path"] = orig_path
                                _base = (_os.environ.get("PUBLIC_BACKEND_URL") or "http://localhost:8000").rstrip('/')
                                images_meta["original_url"] = f"{_base}/static/images/original/{filename}"
                            if proc_path:
                                filename_p = _PURL(proc_path).name
                                images_meta["processed_path"] = proc_path
                                _base = (_os.environ.get("PUBLIC_BACKEND_URL") or "http://localhost:8000").rstrip('/')
                                images_meta["processed_url"] = f"{_base}/static/images/processed/{filename_p}"
                        except Exception:
                            images_meta = images_meta or {}

                        assoc = _TAS()
                        meta_update = {"provenance": provenance or {}, "images": images_meta} if images_meta else {"provenance": provenance or {}}
                        assoc.update_transcription_metadata(str(dossier_id), str(transcription_id), meta_update)
                    except Exception:
                        pass
            except Exception:
                # Non-fatal persistence fallback
                pass

            # Persist base result path if available (dossier run files are already saved by pipeline)
            # Capture minimal result snapshot for UI consumption
            snapshot: Dict[str, Any] = {
                "extracted_text": result.get("extracted_text"),
                "model_used": result.get("model_used"),
                "service_type": result.get("service_type"),
                "tokens_used": result.get("tokens_used"),
                "confidence_score": result.get("confidence_score"),
                "metadata": result.get("metadata", {}),
            }
            self.store.update_status(
                job_id,
                JobStatus.SUCCEEDED,
                finished_at=datetime.utcnow().isoformat(),
                result=snapshot,
            )
            if self.on_status:
                try:
                    self.on_status(job_id, JobStatus.SUCCEEDED.value, {"metadata": result.get("metadata", {})})
                except Exception:
                    pass
            # Publish dossier update event for auto-refresh of dossier manager
            try:
                import asyncio
                from services.dossier.event_bus import event_bus
                asyncio.create_task(event_bus.publish({
                    "type": "dossier:update",
                    "event": "run_completed",
                    "dossier_id": str(dossier_id),
                    "transcription_id": str(transcription_id)
                }))
            except Exception:
                pass
        except Exception as e:
            self.store.update_status(job_id, JobStatus.FAILED, error=str(e), finished_at=datetime.utcnow().isoformat())
            if self.on_status:
                try:
                    self.on_status(job_id, JobStatus.FAILED.value, {"error": str(e)})
                except Exception:
                    pass
        finally:
            # Best-effort cleanup of temp source file
            try:
                import os
                p = job.get("source_path") if isinstance(job, dict) else None
                if p and os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass


_queue_singleton: Optional[ImageToTextQueueService] = None


def get_queue_service() -> ImageToTextQueueService:
    global _queue_singleton
    if _queue_singleton is None:
        store = ImageToTextJobStore()
        processor = ImageToTextProcessorAdapter()
        _queue_singleton = ImageToTextQueueService(store=store, processor=processor)
    return _queue_singleton


