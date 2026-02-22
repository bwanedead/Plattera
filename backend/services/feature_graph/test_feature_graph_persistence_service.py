from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.feature_graph.artifacts import create_bundle_artifact, create_ir_artifact
from backend.feature_graph.models import FeatureGraph
from backend.services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService


def _graph(dossier_id: str, graph_id: str = "g_test") -> FeatureGraph:
    return FeatureGraph.model_validate(
        {
            "graph_id": graph_id,
            "nodes": [
                {
                    "id": "p1",
                    "kind": "point",
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                }
            ],
            "edges": [],
            "metadata": {"dossier_id": dossier_id},
        }
    )


def test_save_artifact_updates_latest_ir_pointer() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = FeatureGraphPersistenceService(
            root=root / "artifacts" / "feature_graphs",
            state_dir=root / "state",
        )
        dossier_id = "D_PTR"
        artifact = create_ir_artifact(
            artifact_id="ir_g_test_001",
            graph=_graph(dossier_id),
            created_by="test",
            source_document_id=dossier_id,
        )
        saved = svc.save_artifact(artifact=artifact, dossier_id=dossier_id)
        latest_path = root / "artifacts" / "feature_graphs" / dossier_id / "latest_ir.json"
        assert latest_path.exists()
        pointer = json.loads(latest_path.read_text(encoding="utf-8"))
        assert pointer["artifact_type"] == "ir"
        assert pointer["artifact_path"] == str(saved["path"])


def test_mark_final_pointers_from_paths_writes_final_ir_and_bundle() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = FeatureGraphPersistenceService(
            root=root / "artifacts" / "feature_graphs",
            state_dir=root / "state",
        )
        dossier_id = "D_FINAL"
        graph = _graph(dossier_id, "g_final")
        ir = create_ir_artifact(
            artifact_id="ir_g_final_001",
            graph=graph,
            created_by="test",
            source_document_id=dossier_id,
        )
        ir_saved = svc.save_artifact(artifact=ir, dossier_id=dossier_id)
        bundle = create_bundle_artifact(
            artifact_id="bundle_g_final_001",
            target_graph=graph,
            parent_artifact_ids=[ir.artifact_id],
            created_by="test",
        )
        bundle_saved = svc.save_artifact(artifact=bundle, dossier_id=dossier_id)

        result = svc.mark_final_pointers_from_paths(
            ir_artifact_path=str(ir_saved["path"]),
            bundle_artifact_path=str(bundle_saved["path"]),
        )
        assert result["success"] is True
        final_ir = root / "artifacts" / "feature_graphs" / dossier_id / "final_ir.json"
        final_bundle = root / "artifacts" / "feature_graphs" / dossier_id / "final_bundle.json"
        assert final_ir.exists()
        assert final_bundle.exists()
