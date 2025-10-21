from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils.id_hash import content_hash


class GeoreferencePersistenceService:
    """
    Persist georeferenced polygons per dossier with atomic writes and a small index.
    Artifacts live under:
      backend/dossiers_data/artifacts/georefs/{dossier_id}/{georef_id}.json
      backend/dossiers_data/artifacts/georefs/{dossier_id}/latest.json
    Index:
      backend/dossiers_data/state/georefs_index.json
    """

    def __init__(self) -> None:
        backend_dir = Path(__file__).resolve().parents[2]
        self._artifacts_root = backend_dir / "dossiers_data" / "artifacts" / "georefs"
        self._state_dir = backend_dir / "dossiers_data" / "state"
        self._index_path = self._state_dir / "georefs_index.json"
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="georef_", suffix=".json", dir=str(path.parent))
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

    def _write_index(self, dossier_id: str, georef_id: str, latest_pointer: Path, saved_at: str, bounds: Dict[str, Any]) -> None:
        idx: Dict[str, Any] = {"georefs": []}
        existing = self._read_json_file(self._index_path)
        if isinstance(existing, dict):
            idx = existing
        # De-duplicate by dossier_id + georef_id
        filtered = [
            e for e in idx.get("georefs", [])
            if not ((e or {}).get("dossier_id") == str(dossier_id) and (e or {}).get("georef_id") == georef_id)
        ]
        filtered.append({
            "dossier_id": dossier_id,
            "georef_id": georef_id,
            "latest_path": str(latest_pointer),
            "bounds": bounds or {},
            "saved_at": saved_at
        })
        idx["georefs"] = sorted(filtered, key=lambda e: e.get("saved_at", ""), reverse=True)
        self._atomic_write(self._index_path, idx)

    def save(self, dossier_id: str, georef_result: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not dossier_id:
            raise ValueError("dossier_id is required")

        core = {
            "geographic_polygon": georef_result.get("geographic_polygon") or {},
            "anchor_info": georef_result.get("anchor_info") or {},
            "projection_metadata": georef_result.get("projection_metadata") or {},
        }
        georef_id = content_hash(core)
        now_iso = datetime.utcnow().isoformat()

        payload = {
            "artifact_type": "georef",
            "georef_id": georef_id,
            "dossier_id": dossier_id,
            "saved_at": now_iso,
            **georef_result,
            "metadata": metadata or {},
            "lineage": {
                "primary_dossier_id": dossier_id,
                "schema_id": georef_result.get("schema_id")
            },
            "frozen_dependencies": {}
        }

        dossier_dir = self._artifacts_root / str(dossier_id)
        dossier_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = dossier_dir / f"{georef_id}.json"
        latest_pointer = dossier_dir / "latest.json"
        self._atomic_write(artifact_path, payload)
        self._atomic_write(latest_pointer, payload)

        bounds = (georef_result.get("geographic_polygon") or {}).get("bounds") or {}
        self._write_index(dossier_id=dossier_id, georef_id=georef_id, latest_pointer=latest_pointer, saved_at=now_iso, bounds=bounds)

        return {"success": True, "georef_id": georef_id, "path": str(artifact_path), "latest": str(latest_pointer)}


