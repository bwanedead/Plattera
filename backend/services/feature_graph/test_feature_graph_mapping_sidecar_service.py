"""Tests for mapping sidecar persistence."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from feature_graph.mapping_artifacts import WorldBBox
from services.feature_graph.feature_graph_mapping_sidecar_service import FeatureGraphMappingSidecarService


def _service(tmp: str) -> FeatureGraphMappingSidecarService:
    root = Path(tmp) / "artifacts" / "feature_graphs"
    return FeatureGraphMappingSidecarService(artifacts_root=root)


def test_persist_sidecars_writes_files_and_descriptors() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = _service(tmp)
        geo = {"type": "FeatureCollection", "features": []}
        clean = b"\x89PNG\r\n\x1a\n" + b"clean-bytes"
        control = b"\x89PNG\r\n\x1a\n" + b"control-bytes"
        bbox = WorldBBox(min_x=0.0, min_y=0.0, max_x=10.0, max_y=10.0)
        result = svc.persist_sidecars(
            dossier_id="D_SIDECAR",
            mapping_id="mapping_test_001",
            geometry_geojson=geo,
            clean_png=clean,
            control_png=control,
            world_bbox=bbox,
            rendered_feature_count=1,
            skipped_feature_count=0,
            image_width=800,
            image_height=600,
        )
        mapping_dir = Path(tmp) / "artifacts" / "feature_graphs" / "D_SIDECAR" / "mappings" / "mapping_test_001"
        assert (mapping_dir / "geometry.geojson").exists()
        assert (mapping_dir / "clean.png").exists()
        assert (mapping_dir / "control.png").exists()
        assert result.geometry.byte_count == len(json.dumps(geo, separators=(",", ":")).encode("utf-8"))
        assert result.clean_render.sha256
        assert result.geometry.ref.startswith("artifact://dossiers/feature_graphs/D_SIDECAR/mappings/mapping_test_001/")
        assert "path" not in json.dumps(result.__dict__, default=str)


def test_sidecar_traversal_and_cross_dossier_paths_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = _service(tmp)
        geo = {"type": "FeatureCollection", "features": []}
        clean = b"clean"
        control = b"control"
        bbox = WorldBBox(min_x=0.0, min_y=0.0, max_x=1.0, max_y=1.0)
        saved = svc.persist_sidecars(
            dossier_id="D_A",
            mapping_id="mapping_a",
            geometry_geojson=geo,
            clean_png=clean,
            control_png=control,
            world_bbox=bbox,
            rendered_feature_count=0,
            skipped_feature_count=0,
            image_width=800,
            image_height=600,
        )
        try:
            svc.resolve_existing_sidecar_path("D_B", "mapping_a", "geometry.geojson")
            assert False, "expected cross-dossier sidecar resolution to fail"
        except Exception as exc:
            assert "feature_graph_sidecar_target_missing" in str(exc)
        try:
            svc.persist_sidecars(
                dossier_id="../escape",
                mapping_id="mapping_bad",
                geometry_geojson=geo,
                clean_png=clean,
                control_png=control,
                world_bbox=bbox,
                rendered_feature_count=0,
                skipped_feature_count=0,
                image_width=800,
                image_height=600,
            )
            assert False, "expected unsafe dossier_id to fail"
        except Exception as exc:
            assert "dossier_id_unsafe_path_characters" in str(exc)
        assert saved.geometry.ref.endswith("geometry.geojson")


def test_resolve_existing_sidecar_rejects_missing_target() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = _service(tmp)
        try:
            svc.resolve_existing_sidecar_path("D_MISSING", "mapping_missing", "clean.png")
            assert False, "expected missing sidecar target to fail"
        except Exception as exc:
            assert "feature_graph_sidecar_target_missing" in str(exc)
