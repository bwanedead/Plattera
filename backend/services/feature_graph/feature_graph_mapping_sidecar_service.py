"""Atomic persistence for feature-graph mapping sidecars."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from config.paths import dossiers_feature_graphs_artifacts_root
from feature_graph.artifact_refs import validate_artifact_id
from feature_graph.mapping_artifacts import (
    GeometryArtifactDescriptor,
    RenderArtifactDescriptor,
    WorldBBox,
)

from feature_graph.path_safety import UnsafeFeatureGraphPathError, require_safe_dossier_id

SidecarName = Literal["geometry.geojson", "clean.png", "control.png"]
ALLOWED_SIDECAR_NAMES = frozenset({"geometry.geojson", "clean.png", "control.png"})


@dataclass(frozen=True)
class PersistedSidecars:
    mapping_id: str
    geometry: GeometryArtifactDescriptor
    clean_render: RenderArtifactDescriptor
    control_render: RenderArtifactDescriptor


class FeatureGraphMappingSidecarService:
    """Persist mapping sidecars under contained dossier/mapping directories."""

    def __init__(self, artifacts_root: Path | None = None) -> None:
        self._artifacts_root = artifacts_root if artifacts_root is not None else dossiers_feature_graphs_artifacts_root()

    def _artifacts_root_resolved(self) -> Path:
        return self._artifacts_root.resolve()

    def _dossier_dir(self, dossier_id: str) -> Path:
        safe_dossier_id = require_safe_dossier_id(dossier_id)
        dossier_dir = (self._artifacts_root / safe_dossier_id).resolve()
        root = self._artifacts_root_resolved()
        if root not in dossier_dir.parents and dossier_dir != root:
            raise UnsafeFeatureGraphPathError("feature_graph_dossier_path_escape")
        return dossier_dir

    def _mapping_dir(self, dossier_id: str, mapping_id: str) -> Path:
        safe_dossier_id = require_safe_dossier_id(dossier_id)
        safe_mapping_id = validate_artifact_id(mapping_id)
        dossier_dir = self._dossier_dir(safe_dossier_id)
        mapping_dir = (dossier_dir / "mappings" / safe_mapping_id).resolve()
        if dossier_dir not in mapping_dir.parents:
            raise UnsafeFeatureGraphPathError("feature_graph_mapping_path_escape")
        return mapping_dir

    def _sidecar_path(self, dossier_id: str, mapping_id: str, sidecar_name: SidecarName) -> Path:
        if sidecar_name not in ALLOWED_SIDECAR_NAMES:
            raise UnsafeFeatureGraphPathError("feature_graph_sidecar_name_invalid")
        mapping_dir = self._mapping_dir(dossier_id, mapping_id)
        sidecar_path = (mapping_dir / sidecar_name).resolve()
        if sidecar_path.parent != mapping_dir:
            raise UnsafeFeatureGraphPathError("feature_graph_sidecar_path_escape")
        return sidecar_path

    def build_sidecar_ref(self, dossier_id: str, mapping_id: str, sidecar_name: SidecarName) -> str:
        safe_dossier_id = require_safe_dossier_id(dossier_id)
        safe_mapping_id = validate_artifact_id(mapping_id)
        if sidecar_name not in ALLOWED_SIDECAR_NAMES:
            raise UnsafeFeatureGraphPathError("feature_graph_sidecar_name_invalid")
        return (
            f"artifact://dossiers/feature_graphs/{safe_dossier_id}/mappings/"
            f"{safe_mapping_id}/{sidecar_name}"
        )

    def _atomic_write_bytes(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix="fg_sidecar_",
            suffix=path.suffix,
            dir=str(path.parent),
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, str(path))
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    @staticmethod
    def _sha256(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def persist_sidecars(
        self,
        *,
        dossier_id: str,
        mapping_id: str,
        geometry_geojson: dict,
        clean_png: bytes,
        control_png: bytes,
        world_bbox: WorldBBox,
        rendered_feature_count: int,
        skipped_feature_count: int,
        image_width: int,
        image_height: int,
    ) -> PersistedSidecars:
        safe_dossier_id = require_safe_dossier_id(dossier_id)
        safe_mapping_id = validate_artifact_id(mapping_id)
        mapping_dir = self._mapping_dir(safe_dossier_id, safe_mapping_id)
        geometry_bytes = json.dumps(geometry_geojson, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        geometry_path = mapping_dir / "geometry.geojson"
        clean_path = mapping_dir / "clean.png"
        control_path = mapping_dir / "control.png"

        self._atomic_write_bytes(geometry_path, geometry_bytes)
        self._atomic_write_bytes(clean_path, clean_png)
        self._atomic_write_bytes(control_path, control_png)

        geometry = GeometryArtifactDescriptor(
            ref=self.build_sidecar_ref(safe_dossier_id, safe_mapping_id, "geometry.geojson"),
            media_type="application/geo+json",
            byte_count=len(geometry_bytes),
            sha256=self._sha256(geometry_bytes),
            world_bbox=world_bbox,
            rendered_feature_count=rendered_feature_count,
            skipped_feature_count=skipped_feature_count,
        )
        clean_render = RenderArtifactDescriptor(
            ref=self.build_sidecar_ref(safe_dossier_id, safe_mapping_id, "clean.png"),
            media_type="image/png",
            profile="clean",
            byte_count=len(clean_png),
            sha256=self._sha256(clean_png),
            width=image_width,
            height=image_height,
            world_bbox=world_bbox,
        )
        control_render = RenderArtifactDescriptor(
            ref=self.build_sidecar_ref(safe_dossier_id, safe_mapping_id, "control.png"),
            media_type="image/png",
            profile="control",
            byte_count=len(control_png),
            sha256=self._sha256(control_png),
            width=image_width,
            height=image_height,
            world_bbox=world_bbox,
        )
        return PersistedSidecars(
            mapping_id=safe_mapping_id,
            geometry=geometry,
            clean_render=clean_render,
            control_render=control_render,
        )

    def resolve_existing_sidecar_path(self, dossier_id: str, mapping_id: str, sidecar_name: SidecarName) -> Path:
        sidecar_path = self._sidecar_path(dossier_id, mapping_id, sidecar_name)
        if not sidecar_path.is_file():
            raise UnsafeFeatureGraphPathError("feature_graph_sidecar_target_missing")
        return sidecar_path
