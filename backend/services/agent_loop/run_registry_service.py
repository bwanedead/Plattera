"""Durable run registry for controller-driven agent-loop runs."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from config.paths import dossiers_state_root


class AgentLoopRunRegistryService:
    def __init__(self, state_dir: Optional[Path] = None) -> None:
        self._state_dir = state_dir if state_dir is not None else dossiers_state_root()
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._state_dir / "agent_loop_runs_index.json"
        self._lock = Lock()

    def create_run(self, *, run_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "run_id": run_id,
            "request_id": request.get("request_id"),
            "dossier_id": request.get("dossier_id"),
            "model": request.get("model"),
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "session_id": None,
            "run_artifact_ref": None,
            "transcript_artifact_ref": None,
            "terminal": None,
            "dashboard": None,
            "error": None,
        }
        with self._lock:
            index = self._read_index()
            runs = [item for item in index.get("runs", []) if item.get("run_id") != run_id]
            runs.append(entry)
            index["runs"] = sorted(runs, key=lambda item: item.get("created_at", ""), reverse=True)
            self._atomic_write(self._index_path, index)
        return entry

    def update_run(self, *, run_id: str, patch: Dict[str, Any]) -> Dict[str, Any] | None:
        with self._lock:
            index = self._read_index()
            runs = list(index.get("runs", []))
            updated = None
            for i, item in enumerate(runs):
                if item.get("run_id") != run_id:
                    continue
                next_item = dict(item)
                next_item.update(patch)
                next_item["updated_at"] = datetime.now(timezone.utc).isoformat()
                runs[i] = next_item
                updated = next_item
                break
            if updated is None:
                return None
            index["runs"] = runs
            self._atomic_write(self._index_path, index)
            return updated

    def get_run(self, run_id: str) -> Dict[str, Any] | None:
        index = self._read_index()
        for item in index.get("runs", []):
            if item.get("run_id") == run_id:
                return item
        return None

    def list_runs(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        index = self._read_index()
        return list(index.get("runs", []))[: max(1, min(limit, 200))]

    def _read_index(self) -> Dict[str, Any]:
        try:
            if not self._index_path.exists():
                return {"runs": []}
            payload = json.loads(self._index_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {"runs": []}

    def _atomic_write(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="agent_loop_", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.replace(tmp_path, str(path))
            except PermissionError:
                with path.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

