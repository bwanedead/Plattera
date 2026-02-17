"""Persistence service for durable Agent Kernel run artifacts."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.agent_kernel.run_artifact import RunArtifact
from backend.config.paths import agent_kernel_artifacts_root, dossiers_state_root


class RunArtifactPersistenceService:
    """
    Persist run artifacts with atomic writes and durable index maintenance.

    Artifacts are stored under:
      dossiers_data/artifacts/agent_kernel/<request_id>/<run_id>.json

    Index is stored at:
      dossiers_data/state/agent_kernel_runs_index.json
    """

    def __init__(self, root: Optional[Path] = None, state_dir: Optional[Path] = None) -> None:
        self._artifacts_root = root if root is not None else agent_kernel_artifacts_root()
        self._state_dir = state_dir if state_dir is not None else dossiers_state_root()
        self._index_path = self._state_dir / "agent_kernel_runs_index.json"
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix="agent_kernel_", suffix=".json", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
                json.dump(data, file_obj, ensure_ascii=False, indent=2)
                file_obj.flush()
                os.fsync(file_obj.fileno())
            os.replace(tmp_path, str(path))
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _read_json_file(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            if not path.exists():
                return None
            with open(path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _update_index(self, run_artifact: RunArtifact, artifact_path: Path, saved_at: str) -> None:
        index: Dict[str, Any] = {"runs": []}
        existing = self._read_json_file(self._index_path)
        if isinstance(existing, dict):
            index = existing

        entries = [
            entry
            for entry in index.get("runs", [])
            if not (
                (entry or {}).get("request_id") == run_artifact.request_id
                and (entry or {}).get("run_id") == run_artifact.run_id
            )
        ]
        entries.append(
            {
                "request_id": run_artifact.request_id,
                "run_id": run_artifact.run_id,
                "artifact_path": str(artifact_path),
                "saved_at": saved_at,
            }
        )
        index["runs"] = sorted(entries, key=lambda item: item.get("saved_at", ""), reverse=True)
        self._atomic_write(self._index_path, index)

    def save_run_artifact(self, run_artifact: RunArtifact) -> Dict[str, Any]:
        artifact_dict = run_artifact.model_dump(mode="json")
        request_dir = self._artifacts_root / str(run_artifact.request_id)
        artifact_path = request_dir / f"{run_artifact.run_id}.json"
        saved_at = datetime.now(timezone.utc).isoformat()

        self._atomic_write(artifact_path, artifact_dict)
        self._update_index(run_artifact=run_artifact, artifact_path=artifact_path, saved_at=saved_at)

        return {
            "success": True,
            "request_id": run_artifact.request_id,
            "run_id": run_artifact.run_id,
            "path": str(artifact_path),
            "saved_at": saved_at,
        }

    def get_run_artifact(self, request_id: str, run_id: str) -> Optional[RunArtifact]:
        artifact_path = self._artifacts_root / str(request_id) / f"{run_id}.json"
        payload = self._read_json_file(artifact_path)
        if payload is None:
            return None
        return RunArtifact.model_validate(payload)

    def list_run_artifacts(self, request_id: Optional[str] = None) -> List[Dict[str, Any]]:
        index = self._read_json_file(self._index_path)
        if not index:
            return []

        entries = index.get("runs", [])
        if request_id is None:
            return entries
        return [entry for entry in entries if (entry or {}).get("request_id") == str(request_id)]
