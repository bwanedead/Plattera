from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Optional, List

from .job_models import ImageToTextJob, JobStatus


class ImageToTextJobStore:
    """
    Simple file-backed store for image-to-text jobs.
    Data is stored under backend/dossiers_data/processing_jobs/image_to_text/jobs.jsonl
    """

    def __init__(self) -> None:
        backend_root = Path(__file__).resolve().parents[2]
        self.store_dir = backend_root / "dossiers_data" / "processing_jobs" / "image_to_text"
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.store_dir / "jobs_index.json"
        self.jobs_dir = self.store_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        if not self.index_file.exists():
            self._write_index({})

    def _read_index(self) -> Dict[str, str]:
        try:
            with self.index_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_index(self, data: Dict[str, str]) -> None:
        tmp = self.index_file.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(self.index_file)

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def create(self, job: ImageToTextJob) -> ImageToTextJob:
        with self._lock:
            index = self._read_index()
            index[job.id] = str(self._job_path(job.id).name)
            self._write_index(index)
            self._write_job(job)
        return job

    def _write_job(self, job: ImageToTextJob) -> None:
        p = self._job_path(job.id)
        with p.open("w", encoding="utf-8") as f:
            json.dump(job.to_dict(), f, indent=2, ensure_ascii=False)

    def get(self, job_id: str) -> Optional[Dict]:
        p = self._job_path(job_id)
        if not p.exists():
            return None
        try:
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def update_status(self, job_id: str, status: JobStatus, **updates) -> Optional[Dict]:
        with self._lock:
            data = self.get(job_id)
            if not data:
                return None
            data["status"] = status.value
            for k, v in updates.items():
                data[k] = v
            p = self._job_path(job_id)
            with p.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return data

    def update_fields(self, job_id: str, **updates) -> Optional[Dict]:
        with self._lock:
            data = self.get(job_id)
            if not data:
                return None
            for k, v in updates.items():
                data[k] = v
            p = self._job_path(job_id)
            with p.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return data

    def list(self, limit: int = 100) -> List[Dict]:
        ids = list(self._read_index().keys())
        out = []
        for jid in ids[-limit:]:
            d = self.get(jid)
            if d:
                out.append(d)
        return out


