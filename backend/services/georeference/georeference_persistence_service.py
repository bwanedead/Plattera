from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List

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
        self._management_dir = backend_dir / "dossiers_data" / "management"

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
            "saved_at": saved_at,
            "dossier_title_snapshot": self._read_dossier_title(dossier_id)
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

        # Derive schema ids for stable single-per-root storage
        schema_id_in = str((georef_result.get("schema_id") or "")).strip()
        schema_root_id = str((georef_result.get("schema_root_id") or "")).strip()
        if not schema_root_id and schema_id_in:
            schema_root_id = schema_id_in[:-3] if schema_id_in.endswith("_v2") else schema_id_in

        # Stable id per root; fallback to content hash if schema context missing
        if schema_root_id:
            georef_id = f"{schema_root_id}_georef"
        else:
            georef_id = content_hash(core)

        now_iso = datetime.utcnow().isoformat()

        # merge metadata and add snapshots
        meta = dict(metadata or {})
        meta.setdefault("dossier_id", str(dossier_id))
        meta.setdefault("dossier_title_snapshot", self._read_dossier_title(dossier_id))

        payload = {
            "artifact_type": "georef",
            "georef_id": georef_id,
            "dossier_id": dossier_id,
            "saved_at": now_iso,
            **georef_result,
            "metadata": meta,
            "lineage": {
                "primary_dossier_id": dossier_id,
                "schema_id": schema_id_in or None,
                "schema_root_id": schema_root_id or None
            },
            "frozen_dependencies": {}
        }

        dossier_dir = self._artifacts_root / str(dossier_id)
        dossier_dir.mkdir(parents=True, exist_ok=True)

        # Remove any prior georefs for the same root (stable-id or legacy hashed)
        if schema_root_id:
            try:
                for p in dossier_dir.glob("*.json"):
                    if p.name == "latest.json":
                        continue
                    obj = self._read_json_file(p) or {}
                    lin = (obj or {}).get("lineage") or {}
                    sid = str(lin.get("schema_id") or "")
                    sroot = str(lin.get("schema_root_id") or "")
                    if sroot == schema_root_id or sid in {schema_root_id, f"{schema_root_id}_v2"}:
                        try:
                            os.remove(p)
                        except Exception:
                            pass
                # Clean index entries for this root's georef id
                try:
                    idx = self._read_json_file(self._index_path) or {"georefs": []}
                    idx["georefs"] = [
                        e for e in idx.get("georefs", [])
                        if not ((e or {}).get("dossier_id") == str(dossier_id) and str((e or {}).get("georef_id") or "") == f"{schema_root_id}_georef")
                    ]
                    self._atomic_write(self._index_path, idx)
                except Exception:
                    pass
            except Exception:
                pass

        artifact_path = dossier_dir / f"{georef_id}.json"
        latest_pointer = dossier_dir / "latest.json"
        self._atomic_write(artifact_path, payload)
        self._atomic_write(latest_pointer, payload)

        bounds = (georef_result.get("geographic_polygon") or {}).get("bounds") or {}
        self._write_index(dossier_id=dossier_id, georef_id=georef_id, latest_pointer=latest_pointer, saved_at=now_iso, bounds=bounds)

        return {"success": True, "georef_id": georef_id, "path": str(artifact_path), "latest": str(latest_pointer)}

    # --------------
    # Title utilities
    # --------------
    def _read_dossier_title(self, dossier_id: str) -> str:
        try:
            mgmt_file = self._management_dir / f"dossier_{dossier_id}.json"
            if mgmt_file.exists():
                with open(mgmt_file, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                return str(data.get("title") or data.get("name") or dossier_id)
        except Exception:
            pass
        return str(dossier_id)

    # --------------
    # Delete helpers
    # --------------
    def delete_georef(self, dossier_id: str, georef_id: str) -> Dict[str, Any]:
        """
        Delete a georeference artifact and remove its index entry. Clears latest.json if it pointed
        to the deleted artifact. Best-effort, returns success flag.
        """
        artifact_path = self._artifacts_root / str(dossier_id) / f"{georef_id}.json"
        latest_pointer = self._artifacts_root / str(dossier_id) / "latest.json"
        removed = False
        try:
            if artifact_path.exists():
                os.remove(artifact_path)
                removed = True
        except Exception:
            removed = False

        # Update index to drop entry
        try:
            idx = self._read_json_file(self._index_path) or {"georefs": []}
            idx["georefs"] = [
                e for e in idx.get("georefs", [])
                if not ((e or {}).get("dossier_id") == str(dossier_id) and (e or {}).get("georef_id") == georef_id)
            ]
            self._atomic_write(self._index_path, idx)
        except Exception:
            pass

        # Clear latest.json if pointing at deleted artifact
        try:
            if latest_pointer.exists():
                with open(latest_pointer, "r", encoding="utf-8") as lf:
                    latest_obj = json.load(lf) or {}
                if latest_obj.get("georef_id") == georef_id:
                    os.remove(latest_pointer)
        except Exception:
            pass

        return {"success": bool(removed)}


