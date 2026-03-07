"""Durable run registry for transcription edit runs."""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from config.paths import dossiers_state_root


class TranscriptionEditRunRegistry:
    _REPLACE_RETRY_ATTEMPTS = 5
    _REPLACE_RETRY_BASE_DELAY_SECONDS = 0.02

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir if state_dir is not None else dossiers_state_root()
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._state_dir / "transcription_edit_runs_index.json"
        self._lock = Lock()

    def create_run(self, *, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "run_id": run_id,
            "status": "running",
            "request": request,
            "created_at": now,
            "updated_at": now,
            "snapshot": None,
            "error": None,
        }
        with self._lock:
            index = self._read_index()
            runs = [item for item in index.get("runs", []) if item.get("run_id") != run_id]
            runs.append(entry)
            index["runs"] = sorted(runs, key=lambda item: item.get("created_at", ""), reverse=True)
            self._atomic_write(self._index_path, index)
        return entry

    def update_run(self, *, run_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            index = self._read_index()
            runs = list(index.get("runs", []))
            updated = None
            for idx, item in enumerate(runs):
                if item.get("run_id") != run_id:
                    continue
                next_item = dict(item)
                next_item.update(patch)
                next_item["updated_at"] = datetime.now(timezone.utc).isoformat()
                runs[idx] = next_item
                updated = next_item
                break
            if updated is None:
                return None
            index["runs"] = runs
            self._atomic_write(self._index_path, index)
            return updated

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        index = self._read_index()
        for item in index.get("runs", []):
            if item.get("run_id") == run_id:
                return item
        return None

    def list_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        index = self._read_index()
        return list(index.get("runs", []))[: max(1, min(limit, 200))]

    def _read_index(self) -> dict[str, Any]:
        try:
            if not self._index_path.exists():
                return {"runs": []}
            payload = json.loads(self._index_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {"runs": []}

    def _atomic_write(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="tx_edit_runs_", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            delay = self._REPLACE_RETRY_BASE_DELAY_SECONDS
            last_error: BaseException | None = None
            for attempt in range(self._REPLACE_RETRY_ATTEMPTS):
                try:
                    os.replace(tmp_path, str(path))
                    return
                except (PermissionError, OSError) as exc:
                    last_error = exc
                    if not _is_transient_replace_error(exc):
                        raise
                    if attempt >= self._REPLACE_RETRY_ATTEMPTS - 1:
                        break
                    time.sleep(delay)
                    delay *= 2.0
            if last_error is not None:
                raise last_error
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass


def _is_transient_replace_error(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError):
        winerror = getattr(exc, "winerror", None)
        errno = getattr(exc, "errno", None)
        if winerror in {5, 32, 33}:
            return True
        if errno in {13, 16}:
            return True
    message = str(exc).lower()
    return "access is denied" in message or "being used by another process" in message
