from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Optional

from config.paths import dossiers_processing_jobs_root
from .job_models import IndexMaintenanceJob, IndexMaintenanceJobStatus


class IndexMaintenanceJobStore:
    """
    File-backed store for index maintenance jobs.
    """

    def __init__(self, store_root: Optional[Path] = None) -> None:
        self.store_dir = store_root or dossiers_processing_jobs_root("index_maintenance")
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

    def create(self, job: IndexMaintenanceJob) -> IndexMaintenanceJob:
        with self._lock:
            index = self._read_index()
            index[job.id] = str(self._job_path(job.id).name)
            self._write_index(index)
            self._write_job(job.to_dict())
        return job

    def _write_job(self, data: Dict) -> None:
        p = self._job_path(data["id"])
        with p.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get(self, job_id: str) -> Optional[Dict]:
        p = self._job_path(job_id)
        if not p.exists():
            return None
        try:
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def update_job(self, job_id: str, data: Dict) -> Optional[Dict]:
        with self._lock:
            if not self._job_path(job_id).exists():
                return None
            self._write_job(data)
            return data

    def update_fields(self, job_id: str, **updates) -> Optional[Dict]:
        with self._lock:
            data = self.get(job_id)
            if not data:
                return None
            for k, v in updates.items():
                data[k] = v
            self._write_job(data)
            return data

    def update_status(self, job_id: str, status: IndexMaintenanceJobStatus, **updates) -> Optional[Dict]:
        return self.update_fields(job_id, status=status.value, **updates)
