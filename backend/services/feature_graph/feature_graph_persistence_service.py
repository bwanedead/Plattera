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
from feature_graph.artifact_refs import validate_artifact_id
from feature_graph.artifacts import (
    IRArtifact,
    CompileArtifact,
    JudgeArtifact,
    BundleArtifact,
)
from feature_graph.mapping_artifacts import MappingArtifact


from feature_graph.path_safety import UnsafeFeatureGraphPathError, require_safe_dossier_id


def _require_safe_dossier_id(dossier_id: str) -> str:
    return require_safe_dossier_id(dossier_id)


ArtifactType = Literal["ir", "compile", "judge", "bundle", "mapping"]
_LATEST_POINTER_NAMES: dict[str, str] = {
    "ir": "latest_ir.json",
    "compile": "latest_compile.json",
    "judge": "latest_judge.json",
    "bundle": "latest_bundle.json",
    "mapping": "latest_mapping.json",
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

    @property
    def artifacts_root(self) -> Path:
        return self._artifacts_root

    def _artifacts_root_resolved(self) -> Path:
        return self._artifacts_root.resolve()

    def _artifact_file_path(self, dossier_id: str, artifact_id: str) -> Path:
        safe_dossier_id = _require_safe_dossier_id(dossier_id)
        safe_artifact_id = validate_artifact_id(artifact_id)
        artifact_path = (self._artifacts_root / safe_dossier_id / f"{safe_artifact_id}.json").resolve()
        root = self._artifacts_root_resolved()
        if root not in artifact_path.parents:
            raise UnsafeFeatureGraphPathError("feature_graph_artifact_path_escape")
        return artifact_path

    def _dossier_dir(self, dossier_id: str) -> Path:
        safe_dossier_id = _require_safe_dossier_id(dossier_id)
        dossier_dir = (self._artifacts_root / safe_dossier_id).resolve()
        root = self._artifacts_root_resolved()
        if root not in dossier_dir.parents and dossier_dir != root:
            raise UnsafeFeatureGraphPathError("feature_graph_dossier_path_escape")
        return dossier_dir

    def _resolve_dossier_artifact_path(
        self,
        *,
        dossier_id: str,
        artifact_path: str,
        artifact_id: Optional[str] = None,
    ) -> tuple[Path, str, str]:
        safe_dossier_id = _require_safe_dossier_id(dossier_id)
        dossier_dir = self._dossier_dir(safe_dossier_id)
        raw = Path(str(artifact_path or "").strip())
        if not str(raw):
            raise UnsafeFeatureGraphPathError("feature_graph_artifact_path_empty")
        try:
            resolved = raw.resolve() if raw.is_absolute() else (dossier_dir / raw).resolve()
        except Exception as exc:
            raise UnsafeFeatureGraphPathError("feature_graph_artifact_path_invalid") from exc
        if dossier_dir not in resolved.parents:
            raise UnsafeFeatureGraphPathError("feature_graph_final_pointer_target_escape")
        if resolved.parent != dossier_dir:
            raise UnsafeFeatureGraphPathError("feature_graph_final_pointer_target_not_in_dossier")
        if resolved.suffix.lower() != ".json":
            raise UnsafeFeatureGraphPathError("feature_graph_final_pointer_target_not_artifact")
        inferred_id = validate_artifact_id(resolved.stem)
        if isinstance(artifact_id, str) and artifact_id.strip():
            validated_id = validate_artifact_id(artifact_id.strip())
            if validated_id != inferred_id:
                raise UnsafeFeatureGraphPathError("feature_graph_final_pointer_artifact_id_mismatch")
        else:
            validated_id = inferred_id
        if not resolved.is_file():
            raise UnsafeFeatureGraphPathError("feature_graph_final_pointer_target_missing")
        return resolved, safe_dossier_id, validated_id

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
        safe_dossier_id = _require_safe_dossier_id(dossier_id)
        pointer_path = self._dossier_dir(safe_dossier_id) / pointer_filename
        payload = {
            "dossier_id": safe_dossier_id,
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
        artifact: IRArtifact | CompileArtifact | JudgeArtifact | BundleArtifact | MappingArtifact,
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
        safe_dossier_id = _require_safe_dossier_id(dossier_id)

        # Serialize artifact to dict
        artifact_dict = artifact.model_dump(mode="json")
        artifact_id = artifact_dict.get("artifact_id")
        artifact_type = artifact_dict.get("artifact_type")

        if not artifact_id or not artifact_type:
            raise ValueError("Artifact must have artifact_id and artifact_type")

        # Determine save location
        artifact_path = self._artifact_file_path(safe_dossier_id, str(artifact_id))
        artifact_path.parent.mkdir(parents=True, exist_ok=True)

        # Get timestamp
        saved_at = artifact_dict.get("metadata", {}).get("created_at")
        if not saved_at:
            saved_at = datetime.utcnow().isoformat()

        # Atomic write
        self._atomic_write(artifact_path, artifact_dict)
        self._update_latest_pointer(
            dossier_id=safe_dossier_id,
            artifact_type=str(artifact_type),
            artifact_id=str(artifact_id),
            artifact_path=artifact_path,
        )

        # Update index
        self._update_index(
            dossier_id=safe_dossier_id,
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
        resolved_path, safe_dossier_id, validated_id = self._resolve_dossier_artifact_path(
            dossier_id=dossier_id,
            artifact_path=artifact_path,
            artifact_id=artifact_id,
        )
        self._write_pointer(
            dossier_id=safe_dossier_id,
            pointer_filename=pointer_name,
            artifact_id=validated_id,
            artifact_type=str(artifact_type),
            artifact_path=resolved_path,
        )
        return {
            "success": True,
            "pointer": str(self._dossier_dir(safe_dossier_id) / pointer_name),
        }

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
        try:
            return _require_safe_dossier_id(str(parts[0]))
        except UnsafeFeatureGraphPathError:
            return None

    def get_artifact(
        self, dossier_id: str, artifact_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve an artifact by dossier_id and artifact_id.

        Returns:
            The artifact dict, or None if not found
        """
        artifact_path = self._artifact_file_path(dossier_id, artifact_id)
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
            safe_dossier_id = _require_safe_dossier_id(dossier_id)
            entries = [e for e in entries if (e or {}).get("dossier_id") == safe_dossier_id]

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
        safe_dossier_id = _require_safe_dossier_id(dossier_id)
        safe_artifact_id = validate_artifact_id(artifact_id)
        artifact_path = self._artifact_file_path(safe_dossier_id, safe_artifact_id)

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
                    (e or {}).get("dossier_id") == safe_dossier_id
                    and (e or {}).get("artifact_id") == safe_artifact_id
                )
            ]
            self._atomic_write(self._index_path, idx)
        except Exception:
            pass

        return {"success": bool(removed)}
