"""
Feature Graph Persistence Service
==================================

Persists feature graph artifacts (IR, compile, judge, bundle) with atomic writes and index maintenance.

Design principles:
- Atomic writes: use temp file + os.replace for crash-safety
- Index maintenance: maintain a queryable index of all artifacts
- Lineage tracking: parent_artifact_ids preserved in metadata
- Separate from legacy pipelines: keep feature graph artifacts isolated
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List, Literal

from config.paths import dossiers_feature_graphs_artifacts_root, dossiers_state_root
from feature_graph.artifacts import (
    IRArtifact,
    CompileArtifact,
    JudgeArtifact,
    BundleArtifact,
)


ArtifactType = Literal["ir", "compile", "judge", "bundle"]
_LATEST_POINTER_NAMES: dict[str, str] = {
    "ir": "latest_ir.json",
    "compile": "latest_compile.json",
    "judge": "latest_judge.json",
    "bundle": "latest_bundle.json",
}
_FINAL_POINTER_NAMES: dict[str, str] = {
    "ir": "final_ir.json",
    "bundle": "final_bundle.json",
}


class FeatureGraphPersistenceService:
    """
    Persist feature graph artifacts with atomic writes and index maintenance.

    Artifacts are stored under:
      dossiers_data/artifacts/feature_graphs/<dossier_id>/<artifact_id>.json

    Index is stored at:
      dossiers_data/state/feature_graphs_index.json
    """

    def __init__(self, root: Optional[Path] = None, state_dir: Optional[Path] = None) -> None:
        """
        Initialize persistence service.

        Args:
            root: Optional override for artifacts root (used in tests with temp dirs)
            state_dir: Optional override for state directory (used in tests with temp dirs)
        """
        self._artifacts_root = root if root is not None else dossiers_feature_graphs_artifacts_root()
        self._state_dir = state_dir if state_dir is not None else dossiers_state_root()
        self._index_path = self._state_dir / "feature_graphs_index.json"
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, data: Dict[str, Any]) -> None:
        """
        Atomically write JSON data to a file using temp file + os.replace.

        This ensures crash-safety: either the full write succeeds or the old file is unchanged.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix="fg_artifact_", suffix=".json", dir=str(path.parent)
        )
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
        """Read JSON file, returning None if missing or corrupt."""
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception:
            return None
        return None

    def _write_pointer(
        self,
        *,
        dossier_id: str,
        pointer_filename: str,
        artifact_id: str,
        artifact_type: str,
        artifact_path: Path,
    ) -> None:
        pointer_path = self._artifacts_root / str(dossier_id) / pointer_filename
        payload = {
            "dossier_id": str(dossier_id),
            "artifact_id": str(artifact_id),
            "artifact_type": str(artifact_type),
            "artifact_path": str(artifact_path),
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        self._atomic_write(pointer_path, payload)

    def _update_latest_pointer(
        self,
        *,
        dossier_id: str,
        artifact_type: str,
        artifact_id: str,
        artifact_path: Path,
    ) -> None:
        pointer_name = _LATEST_POINTER_NAMES.get(str(artifact_type))
        if pointer_name is None:
            return
        self._write_pointer(
            dossier_id=dossier_id,
            pointer_filename=pointer_name,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            artifact_path=artifact_path,
        )

    def _update_index(
        self,
        dossier_id: str,
        artifact_id: str,
        artifact_type: ArtifactType,
        saved_at: str,
        artifact_path: Path,
    ) -> None:
        """
        Update the feature graphs index with a new artifact entry.

        Index structure:
        {
          "artifacts": [
            {
              "dossier_id": str,
              "artifact_id": str,
              "artifact_type": str,
              "artifact_path": str,
              "saved_at": str
            },
            ...
          ]
        }

        Entries are deduplicated by (dossier_id, artifact_id) and sorted by saved_at desc.
        """
        index: Dict[str, Any] = {"artifacts": []}
        existing = self._read_json_file(self._index_path)
        if isinstance(existing, dict):
            index = existing

        # Remove any existing entry for this (dossier_id, artifact_id)
        entries = [
            e
            for e in index.get("artifacts", [])
            if not (
                (e or {}).get("dossier_id") == str(dossier_id)
                and (e or {}).get("artifact_id") == artifact_id
            )
        ]

        # Add new entry
        entries.append(
            {
                "dossier_id": dossier_id,
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "artifact_path": str(artifact_path),
                "saved_at": saved_at,
            }
        )

        # Sort by saved_at desc (most recent first)
        index["artifacts"] = sorted(
            entries, key=lambda e: e.get("saved_at", ""), reverse=True
        )

        self._atomic_write(self._index_path, index)

    def save_artifact(
        self,
        artifact: IRArtifact | CompileArtifact | JudgeArtifact | BundleArtifact,
        dossier_id: str,
    ) -> Dict[str, Any]:
        """
        Save a feature graph artifact to disk and update the index.

        Args:
            artifact: The artifact to save (IR, compile, judge, or bundle)
            dossier_id: The dossier this artifact belongs to

        Returns:
            Dict with success status, artifact_id, and path
        """
        if not dossier_id:
            raise ValueError("dossier_id is required")

        # Serialize artifact to dict
        artifact_dict = artifact.model_dump(mode="json")
        artifact_id = artifact_dict.get("artifact_id")
        artifact_type = artifact_dict.get("artifact_type")

        if not artifact_id or not artifact_type:
            raise ValueError("Artifact must have artifact_id and artifact_type")

        # Determine save location
        artifacts_dir = self._artifacts_root / str(dossier_id)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifacts_dir / f"{artifact_id}.json"

        # Get timestamp
        saved_at = artifact_dict.get("metadata", {}).get("created_at")
        if not saved_at:
            saved_at = datetime.utcnow().isoformat()

        # Atomic write
        self._atomic_write(artifact_path, artifact_dict)
        self._update_latest_pointer(
            dossier_id=str(dossier_id),
            artifact_type=str(artifact_type),
            artifact_id=str(artifact_id),
            artifact_path=artifact_path,
        )

        # Update index
        self._update_index(
            dossier_id=dossier_id,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            saved_at=saved_at,
            artifact_path=artifact_path,
        )

        return {
            "success": True,
            "artifact_id": artifact_id,
            "path": str(artifact_path),
        }

    def mark_final_pointer(
        self,
        *,
        dossier_id: str,
        artifact_type: Literal["ir", "bundle"],
        artifact_path: str,
        artifact_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        pointer_name = _FINAL_POINTER_NAMES.get(str(artifact_type))
        if pointer_name is None:
            raise ValueError(f"unsupported_final_pointer_type:{artifact_type}")
        path = Path(artifact_path)
        if not artifact_id:
            artifact_id = path.stem
        self._write_pointer(
            dossier_id=str(dossier_id),
            pointer_filename=pointer_name,
            artifact_id=str(artifact_id),
            artifact_type=str(artifact_type),
            artifact_path=path,
        )
        return {"success": True, "pointer": str(self._artifacts_root / str(dossier_id) / pointer_name)}

    def mark_final_pointers_from_paths(
        self,
        *,
        ir_artifact_path: Optional[str],
        bundle_artifact_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        written: list[str] = []
        dossier_id = None
        if ir_artifact_path:
            dossier_id = self._dossier_id_from_artifact_path(ir_artifact_path)
            if dossier_id:
                self.mark_final_pointer(
                    dossier_id=dossier_id,
                    artifact_type="ir",
                    artifact_path=ir_artifact_path,
                )
                written.append("final_ir.json")
        if bundle_artifact_path and dossier_id:
            self.mark_final_pointer(
                dossier_id=dossier_id,
                artifact_type="bundle",
                artifact_path=bundle_artifact_path,
            )
            written.append("final_bundle.json")
        return {"success": bool(written), "dossier_id": dossier_id, "written": written}

    def _dossier_id_from_artifact_path(self, artifact_path: str) -> Optional[str]:
        try:
            path = Path(artifact_path).resolve()
            root = self._artifacts_root.resolve()
        except Exception:
            return None
        if root not in path.parents:
            return None
        rel = path.relative_to(root)
        parts = rel.parts
        if not parts:
            return None
        return str(parts[0])

    def get_artifact(
        self, dossier_id: str, artifact_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve an artifact by dossier_id and artifact_id.

        Returns:
            The artifact dict, or None if not found
        """
        artifact_path = self._artifacts_root / str(dossier_id) / f"{artifact_id}.json"
        return self._read_json_file(artifact_path)

    def list_artifacts(
        self, dossier_id: Optional[str] = None, artifact_type: Optional[ArtifactType] = None
    ) -> List[Dict[str, Any]]:
        """
        List artifacts, optionally filtered by dossier_id and/or artifact_type.

        Returns:
            List of index entries (dossier_id, artifact_id, artifact_type, artifact_path, saved_at)
        """
        index = self._read_json_file(self._index_path)
        if not index:
            return []

        entries = index.get("artifacts", [])

        # Filter by dossier_id if provided
        if dossier_id is not None:
            entries = [e for e in entries if (e or {}).get("dossier_id") == str(dossier_id)]

        # Filter by artifact_type if provided
        if artifact_type is not None:
            entries = [e for e in entries if (e or {}).get("artifact_type") == artifact_type]

        return entries

    def list_all_artifacts(self) -> List[Dict[str, Any]]:
        """
        List all artifacts across all dossiers.

        Returns:
            List of index entries sorted by saved_at desc
        """
        return self.list_artifacts()

    def delete_artifact(self, dossier_id: str, artifact_id: str) -> Dict[str, Any]:
        """
        Delete an artifact from disk and remove from index.

        Args:
            dossier_id: The dossier the artifact belongs to
            artifact_id: The artifact ID to delete

        Returns:
            Dict with success status
        """
        artifact_path = self._artifacts_root / str(dossier_id) / f"{artifact_id}.json"

        removed = False
        try:
            if artifact_path.exists():
                os.remove(artifact_path)
                removed = True
        except Exception:
            removed = False

        # Update index to remove this entry
        try:
            idx = self._read_json_file(self._index_path) or {"artifacts": []}
            idx["artifacts"] = [
                e
                for e in idx.get("artifacts", [])
                if not (
                    (e or {}).get("dossier_id") == str(dossier_id)
                    and (e or {}).get("artifact_id") == artifact_id
                )
            ]
            self._atomic_write(self._index_path, idx)
        except Exception:
            pass

        return {"success": bool(removed)}
