
from __future__ import annotations

import json
import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class SchemaPersistenceService:
    """
    Persist Text-to-Schema results per dossier with an atomic write strategy and index maintenance.
    """

    def __init__(self) -> None:
        backend_dir = Path(__file__).resolve().parents[2]
        self._jobs_root = backend_dir / "dossiers_data" / "processing_jobs" / "text_to_schema"
        self._state_dir = backend_dir / "dossiers_data" / "state"
        self._index_path = self._state_dir / "text_to_schema_index.json"
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
        sha = hashlib.sha256((original_text or "").encode("utf-8")).hexdigest()
        dossier_dir = self._jobs_root / str(dossier_id)
        dossier_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "dossier_id": dossier_id,
            "saved_at": now_iso,
            "model_used": model_used,
            "original_text_length": len(original_text or ""),
            "original_text_sha256": sha,
            "structured_data": structured_data,
            "metadata": metadata or {},
        }

        # Write versioned file and latest pointer
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        versioned_path = dossier_dir / f"schema_{ts}.json"
        latest_path = dossier_dir / "latest.json"
        self._atomic_write(versioned_path, payload)
        self._atomic_write(latest_path, payload)

        # Update index
        index: Dict[str, Any] = {"schemas": []}
        if self._index_path.exists():
            try:
                with open(self._index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        index = data
            except Exception:
                index = {"schemas": []}

        entries = [e for e in index.get("schemas", []) if (e or {}).get("dossier_id") != str(dossier_id)]
        entries.append({
            "dossier_id": dossier_id,
            "latest_saved_at": now_iso,
            "latest_sha256": sha,
            "latest_length": len(original_text or ""),
            "model_used": model_used,
        })
        index["schemas"] = sorted(entries, key=lambda e: e.get("latest_saved_at", ""), reverse=True)
        self._atomic_write(self._index_path, index)

        return {
            "success": True,
            "path": str(versioned_path),
            "latest": str(latest_path),
        }


