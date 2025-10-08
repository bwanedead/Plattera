"""
Final Registry Service
======================

Canonical per-dossier registry mapping segment_id to strict versioned draft_id
that represents the final (representative) draft for that segment.

Storage path per dossier:
  backend/dossiers_data/state/{dossier_id}/final_registry.json

Schema:
{
  "segments": {
    "{segment_id}": {
      "transcription_id": "...",
      "draft_id": "{strict_versioned_id}",
      "set_at": "ISO8601",
      "set_by": "optional_user"
    }
  },
  "_version": 1
}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import json
from datetime import datetime
import os
import tempfile


class FinalRegistryService:
    def __init__(self) -> None:
        self._backend_root = Path(__file__).resolve().parents[2]

    # ---------------- Internal helpers ----------------
    def _registry_path(self, dossier_id: str) -> Path:
        state_dir = self._backend_root / "dossiers_data" / "state" / str(dossier_id)
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir / "final_registry.json"

    def _read_registry(self, dossier_id: str) -> Dict[str, Any]:
        path = self._registry_path(dossier_id)
        if not path.exists():
            return {"segments": {}, "_version": 1}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return {"segments": {}, "_version": 1}
                data.setdefault("segments", {})
                data.setdefault("_version", 1)
                return data
        except Exception:
            return {"segments": {}, "_version": 1}

    def _atomic_write(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path_str = tempfile.mkstemp(prefix="final_registry_", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_f:
                json.dump(data, tmp_f, indent=2, ensure_ascii=False)
                tmp_f.flush()
                os.fsync(tmp_f.fileno())
            os.replace(tmp_path_str, str(path))
        finally:
            try:
                if os.path.exists(tmp_path_str):
                    os.remove(tmp_path_str)
            except Exception:
                pass

    # ---------------- Public API ----------------
    def list_finals(self, dossier_id: str) -> Dict[str, Dict[str, Any]]:
        reg = self._read_registry(dossier_id)
        return reg.get("segments", {})

    def get_segment_final(self, dossier_id: str, segment_id: str) -> Optional[Dict[str, Any]]:
        reg = self._read_registry(dossier_id)
        segs = reg.get("segments", {})
        val = segs.get(str(segment_id))
        return val if isinstance(val, dict) else None

    def set_segment_final(
        self,
        dossier_id: str,
        segment_id: str,
        transcription_id: str,
        draft_id: str,
        set_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(dossier_id, str) or not dossier_id:
            raise ValueError("dossier_id required")
        if not isinstance(segment_id, str) or not segment_id:
            raise ValueError("segment_id required")
        if not isinstance(transcription_id, str) or not transcription_id:
            raise ValueError("transcription_id required")
        if not isinstance(draft_id, str) or not draft_id:
            raise ValueError("draft_id required")

        reg = self._read_registry(dossier_id)
        segs = reg.setdefault("segments", {})
        segs[str(segment_id)] = {
            "transcription_id": transcription_id,
            "draft_id": draft_id,
            "set_at": datetime.utcnow().isoformat(),
            "set_by": set_by,
        }
        self._atomic_write(self._registry_path(dossier_id), reg)
        return segs[str(segment_id)]

    def clear_segment_final(self, dossier_id: str, segment_id: str) -> bool:
        reg = self._read_registry(dossier_id)
        segs = reg.setdefault("segments", {})
        removed = segs.pop(str(segment_id), None)
        self._atomic_write(self._registry_path(dossier_id), reg)
        return removed is not None


