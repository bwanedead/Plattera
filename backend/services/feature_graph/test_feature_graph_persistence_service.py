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


def test_save_artifact_rejects_unsafe_dossier_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = FeatureGraphPersistenceService(
            root=root / "artifacts" / "feature_graphs",
            state_dir=root / "state",
        )
        artifact = create_ir_artifact(
            artifact_id="ir_safe_001",
            graph=_graph("D_SAFE"),
            created_by="test",
            source_document_id="D_SAFE",
        )
        try:
            svc.save_artifact(artifact=artifact, dossier_id="../escape")
            assert False, "expected unsafe dossier_id to be rejected"
        except Exception as exc:
            assert "dossier_id_unsafe_path_characters" in str(exc)


def test_get_artifact_rejects_unsafe_dossier_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = FeatureGraphPersistenceService(
            root=root / "artifacts" / "feature_graphs",
            state_dir=root / "state",
        )
        try:
            svc.get_artifact("../escape", "ir_safe_001")
            assert False, "expected unsafe dossier_id to be rejected"
        except Exception as exc:
            assert "dossier_id_unsafe_path_characters" in str(exc)


def test_delete_artifact_rejects_unsafe_artifact_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = FeatureGraphPersistenceService(
            root=root / "artifacts" / "feature_graphs",
            state_dir=root / "state",
        )
        try:
            svc.delete_artifact("D_SAFE", "../escape")
            assert False, "expected unsafe artifact_id to be rejected"
        except Exception as exc:
            assert "feature_graph_artifact_id_invalid" in str(exc)


def test_mark_final_pointer_rejects_external_artifact_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = FeatureGraphPersistenceService(
            root=root / "artifacts" / "feature_graphs",
            state_dir=root / "state",
        )
        dossier_id = "D_PTR_CONTAIN"
        graph = _graph(dossier_id)
        ir = create_ir_artifact(
            artifact_id="ir_contain_001",
            graph=graph,
            created_by="test",
            source_document_id=dossier_id,
        )
        saved = svc.save_artifact(artifact=ir, dossier_id=dossier_id)
        external_path = root / "outside" / "ir_contain_001.json"
        external_path.parent.mkdir(parents=True, exist_ok=True)
        external_path.write_text("{}", encoding="utf-8")

        try:
            svc.mark_final_pointer(
                dossier_id=dossier_id,
                artifact_type="ir",
                artifact_path=str(external_path),
            )
            assert False, "expected external artifact_path to be rejected"
        except Exception as exc:
            assert "feature_graph_final_pointer_target_escape" in str(exc)

        pointer = svc.mark_final_pointer(
            dossier_id=dossier_id,
            artifact_type="ir",
            artifact_path=str(saved["path"]),
        )
        assert pointer["success"] is True
        final_ir = root / "artifacts" / "feature_graphs" / dossier_id / "final_ir.json"
        payload = json.loads(final_ir.read_text(encoding="utf-8"))
        assert payload["artifact_id"] == "ir_contain_001"
        assert payload["dossier_id"] == dossier_id
        assert payload["artifact_path"] == str(saved["path"])


def test_mark_final_pointer_rejects_other_dossier_artifact_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = FeatureGraphPersistenceService(
            root=root / "artifacts" / "feature_graphs",
            state_dir=root / "state",
        )
        graph_a = _graph("D_A", "g_a")
        graph_b = _graph("D_B", "g_b")
        saved_a = svc.save_artifact(
            artifact=create_ir_artifact(
                artifact_id="ir_other_dossier",
                graph=graph_a,
                created_by="test",
                source_document_id="D_A",
            ),
            dossier_id="D_A",
        )
        try:
            svc.mark_final_pointer(
                dossier_id="D_B",
                artifact_type="ir",
                artifact_path=str(saved_a["path"]),
            )
            assert False, "expected cross-dossier artifact_path to be rejected"
        except Exception as exc:
            assert "feature_graph_final_pointer_target_escape" in str(exc)


def test_save_artifact_normalizes_dossier_id_in_pointer_and_index() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = FeatureGraphPersistenceService(
            root=root / "artifacts" / "feature_graphs",
            state_dir=root / "state",
        )
        dossier_id = "D_NORM"
        artifact = create_ir_artifact(
            artifact_id="ir_norm_001",
            graph=_graph(dossier_id),
            created_by="test",
            source_document_id=dossier_id,
        )
        svc.save_artifact(artifact=artifact, dossier_id=f"  {dossier_id}  ")

        latest_path = root / "artifacts" / "feature_graphs" / dossier_id / "latest_ir.json"
        pointer = json.loads(latest_path.read_text(encoding="utf-8"))
        assert pointer["dossier_id"] == dossier_id

        index = json.loads((root / "state" / "feature_graphs_index.json").read_text(encoding="utf-8"))
        assert index["artifacts"][0]["dossier_id"] == dossier_id


def test_mark_final_pointer_rejects_missing_target() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = FeatureGraphPersistenceService(
            root=root / "artifacts" / "feature_graphs",
            state_dir=root / "state",
        )
        dossier_id = "D_FINAL_MISSING"
        try:
            svc.mark_final_pointer(
                dossier_id=dossier_id,
                artifact_type="ir",
                artifact_path=str(root / "artifacts" / "feature_graphs" / dossier_id / "missing.json"),
            )
            assert False, "expected missing final pointer target to be rejected"
        except Exception as exc:
            assert "feature_graph_final_pointer_target_missing" in str(exc)


def test_mark_final_artifacts_writes_ir_and_bundle_pointers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = FeatureGraphPersistenceService(
            root=root / "artifacts" / "feature_graphs",
            state_dir=root / "state",
        )
        dossier_id = "D_FINAL_TX"
        graph = _graph(dossier_id, "g_final_tx")
        ir = create_ir_artifact(
            artifact_id="ir_final_tx_001",
            graph=graph,
            created_by="test",
            source_document_id=dossier_id,
        )
        ir_saved = svc.save_artifact(artifact=ir, dossier_id=dossier_id)
        bundle = create_bundle_artifact(
            artifact_id="bundle_final_tx_001",
            target_graph=graph,
            parent_artifact_ids=[ir.artifact_id],
            created_by="test",
        )
        bundle_saved = svc.save_artifact(artifact=bundle, dossier_id=dossier_id)

        result = svc.mark_final_artifacts(
            dossier_id=dossier_id,
            targets={
                "ir": ir.artifact_id,
                "bundle": bundle.artifact_id,
            },
        )
        assert result["success"] is True
        final_ir = json.loads(
            (root / "artifacts" / "feature_graphs" / dossier_id / "final_ir.json").read_text(
                encoding="utf-8"
            )
        )
        final_bundle = json.loads(
            (root / "artifacts" / "feature_graphs" / dossier_id / "final_bundle.json").read_text(
                encoding="utf-8"
            )
        )
        assert final_ir["artifact_path"] == str(ir_saved["path"])
        assert final_bundle["artifact_path"] == str(bundle_saved["path"])


def test_mark_final_artifacts_restores_snapshots_when_second_write_fails(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        svc = FeatureGraphPersistenceService(
            root=root / "artifacts" / "feature_graphs",
            state_dir=root / "state",
        )
        dossier_id = "D_FINAL_ROLLBACK"
        graph_a = _graph(dossier_id, "g_a")
        graph_b = _graph(dossier_id, "g_b")
        ir_a = create_ir_artifact(
            artifact_id="ir_final_a",
            graph=graph_a,
            created_by="test",
            source_document_id=dossier_id,
        )
        ir_b = create_ir_artifact(
            artifact_id="ir_final_b",
            graph=graph_b,
            created_by="test",
            source_document_id=dossier_id,
        )
        svc.save_artifact(artifact=ir_a, dossier_id=dossier_id)
        svc.save_artifact(artifact=ir_b, dossier_id=dossier_id)
        bundle_a = create_bundle_artifact(
            artifact_id="bundle_final_a",
            target_graph=graph_a,
            parent_artifact_ids=[ir_a.artifact_id],
            created_by="test",
        )
        bundle_b = create_bundle_artifact(
            artifact_id="bundle_final_b",
            target_graph=graph_b,
            parent_artifact_ids=[ir_b.artifact_id],
            created_by="test",
        )
        svc.save_artifact(artifact=bundle_a, dossier_id=dossier_id)
        svc.save_artifact(artifact=bundle_b, dossier_id=dossier_id)

        svc.mark_final_artifacts(
            dossier_id=dossier_id,
            targets={"ir": ir_a.artifact_id, "bundle": bundle_a.artifact_id},
        )
        final_ir_path = root / "artifacts" / "feature_graphs" / dossier_id / "final_ir.json"
        final_bundle_path = root / "artifacts" / "feature_graphs" / dossier_id / "final_bundle.json"
        before_ir = final_ir_path.read_bytes()
        before_bundle = final_bundle_path.read_bytes()

        original_write = FeatureGraphPersistenceService._write_pointer
        call_count = {"n": 0}

        def _fail_on_second_write(self, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise ValueError("final_pointer_write_failed")
            return original_write(self, **kwargs)

        monkeypatch.setattr(FeatureGraphPersistenceService, "_write_pointer", _fail_on_second_write)

        try:
            svc.mark_final_artifacts(
                dossier_id=dossier_id,
                targets={"ir": ir_b.artifact_id, "bundle": bundle_b.artifact_id},
            )
            assert False, "expected second pointer write failure"
        except ValueError as exc:
            assert "final_pointer_write_failed" in str(exc)

        assert final_ir_path.read_bytes() == before_ir
        assert final_bundle_path.read_bytes() == before_bundle
