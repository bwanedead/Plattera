
from __future__ import annotations

import json
import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils.id_hash import content_hash


class SchemaPersistenceService:
    """
    Persist Text-to-Schema results per dossier with an atomic write strategy and index maintenance.
    """

    def __init__(self) -> None:
        backend_dir = Path(__file__).resolve().parents[2]
        self._jobs_root = backend_dir / "dossiers_data" / "processing_jobs" / "text_to_schema"
        # New artifact store (schemas)
        self._artifacts_root = backend_dir / "dossiers_data" / "artifacts" / "schemas"
        # Indices
        self._state_dir = backend_dir / "dossiers_data" / "state"
        self._schemas_index_path = self._state_dir / "schemas_index.json"
        self._legacy_index_path = self._state_dir / "text_to_schema_index.json"
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="schema_", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(path))
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _read_json_file(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception:
            return None
        return None

    def _write_schemas_index(self, dossier_id: str, schema_id: str, latest_pointer: Path, saved_at: str) -> None:
        index: Dict[str, Any] = {"schemas": []}
        existing = self._read_json_file(self._schemas_index_path)
        if isinstance(existing, dict):
            index = existing

        entries = [e for e in index.get("schemas", []) if (e or {}).get("dossier_id") != str(dossier_id)]
        entries.append({
            "dossier_id": dossier_id,
            "schema_id": schema_id,
            "latest_path": str(latest_pointer),
            "saved_at": saved_at
        })
        index["schemas"] = sorted(entries, key=lambda e: e.get("saved_at", ""), reverse=True)
        self._atomic_write(self._schemas_index_path, index)

    def _write_legacy_index(self, dossier_id: str, now_iso: str, sha: str, original_text_len: int, model_used: Optional[str]) -> None:
        # Preserve existing index format for compatibility
        index: Dict[str, Any] = {"schemas": []}
        existing = self._read_json_file(self._legacy_index_path)
        if isinstance(existing, dict):
            index = existing
        entries = [e for e in index.get("schemas", []) if (e or {}).get("dossier_id") != str(dossier_id)]
        entries.append({
            "dossier_id": dossier_id,
            "latest_saved_at": now_iso,
            "latest_sha256": sha,
            "latest_length": original_text_len,
            "model_used": model_used,
        })
        index["schemas"] = sorted(entries, key=lambda e: e.get("latest_saved_at", ""), reverse=True)
        self._atomic_write(self._legacy_index_path, index)

    def save(
        self,
        dossier_id: str,
        structured_data: Dict[str, Any],
        original_text: str,
        model_used: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not dossier_id or not structured_data:
            raise ValueError("dossier_id and structured_data are required")

        now_iso = datetime.utcnow().isoformat()
        text_sha = hashlib.sha256((original_text or "").encode("utf-8")).hexdigest()

        # Stable schema id from the structured_data content
        schema_id = content_hash(structured_data)

        # Build payload (include reserved lineage placeholders)
        payload = {
            "artifact_type": "schema",
            "schema_id": schema_id,
            "dossier_id": dossier_id,
            "saved_at": now_iso,
            "model_used": model_used,
            "original_text_length": len(original_text or ""),
            "original_text_sha256": text_sha,
            "original_text": original_text or "",
            "structured_data": structured_data,
            "metadata": metadata or {},
            "lineage": {
                "primary_dossier_id": dossier_id
            },
            "frozen_dependencies": {}
        }

        # New artifact store (immutable per schema_id) + latest pointer
        artifacts_dir = self._artifacts_root / str(dossier_id)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifacts_dir / f"{schema_id}.json"
        latest_pointer_artifacts = artifacts_dir / "latest.json"
        self._atomic_write(artifact_path, payload)
        self._atomic_write(latest_pointer_artifacts, payload)

        # Legacy processing_jobs layout (dual-write for compatibility)
        dossier_dir = self._jobs_root / str(dossier_id)
        dossier_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        versioned_path = dossier_dir / f"schema_{ts}.json"
        latest_path = dossier_dir / "latest.json"
        self._atomic_write(versioned_path, payload)
        self._atomic_write(latest_path, payload)

        # Update indices
        self._write_schemas_index(dossier_id=dossier_id, schema_id=schema_id, latest_pointer=latest_pointer_artifacts, saved_at=now_iso)
        self._write_legacy_index(dossier_id=dossier_id, now_iso=now_iso, sha=text_sha, original_text_len=len(original_text or ""), model_used=model_used)

        return {
            "success": True,
            "schema_id": schema_id,
            "path": str(artifact_path),
            "latest": str(latest_pointer_artifacts),
        }


