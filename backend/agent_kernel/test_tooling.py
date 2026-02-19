"""Tests for concrete kernel tool dependency integrations."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config.paths as legacy_paths
from backend.agent_kernel.run_artifact import ArtifactRef
from backend.agent_kernel.tooling import (
    CorpusArtifactOpener,
    CorpusDeedHydrator,
    DraftIRFilesystemProposer,
    FeatureGraphBundlerTool,
    FeatureGraphCompilerTool,
    FeatureGraphJudgeTool,
    RetrievalEvidenceTool,
)
from backend.retrieval.evidence.models import RetrievalResult
from backend.services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService


def _write_json(path: Path, obj: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_hydrate_deed_uses_corpus_provider_and_persists_artifact() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_legacy_dossiers_root = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            dossier_id = "D_TOOLING"
            finalized = (
                _patched_root()
                / "views"
                / "transcriptions"
                / dossier_id
                / "final"
                / "dossier_final.json"
            )
            _write_json(
                finalized,
                {
                    "dossier_id": dossier_id,
                    "dossier_title": "Tooling Test",
                    "generated_at": "2026-01-01T00:00:00Z",
                    "stitched_text": "Hydrated deed body",
                    "sha256": "dummy",
                },
            )
            hydrator = CorpusDeedHydrator()
            result = hydrator.hydrate_deed({"dossier_id": dossier_id})

            artifact_ref = ArtifactRef.model_validate(result["artifact_ref"])
            payload = json.loads(Path(artifact_ref.artifact_path).read_text(encoding="utf-8"))
            assert result["reason_codes"] == ["deed_hydrated"]
            assert payload["artifact_type"] == "hydrated_deed"
            assert payload["text"] == "Hydrated deed body"
        finally:
            legacy_paths.dossiers_root = original_legacy_dossiers_root  # type: ignore[assignment]


def test_open_artifact_summarizes_referenced_json_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "artifact.json"
        _write_json(path, {"alpha": 1, "beta": 2})
        opener = CorpusArtifactOpener()
        result = opener.open_artifact({"artifact_ref": {"artifact_path": str(path)}})

        assert result["reason_codes"] == ["artifact_opened"]
        assert str(result["summary"]).startswith("json_keys=")


def test_draft_ir_proposer_persists_stub_artifact_ref() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_legacy_dossiers_root = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            proposer = DraftIRFilesystemProposer()
            ref = proposer.draft_ir({"dossier_id": "D_DRAFT"})

            payload = json.loads(Path(ref.artifact_path).read_text(encoding="utf-8"))
            assert payload["artifact_type"] == "ir_draft_stub"
            assert payload["dossier_id"] == "D_DRAFT"
            assert "graph" in payload
            assert str(payload["graph"].get("graph_id", "")).startswith("graph_draft_")
        finally:
            legacy_paths.dossiers_root = original_legacy_dossiers_root  # type: ignore[assignment]


def test_feature_graph_compiler_and_judge_tools_persist_artifact_refs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fg_persistence = FeatureGraphPersistenceService(
            root=root / "dossiers_data" / "artifacts" / "feature_graphs",
            state_dir=root / "dossiers_data" / "state",
        )
        compiler = FeatureGraphCompilerTool(persistence=fg_persistence)
        judge = FeatureGraphJudgeTool(persistence=fg_persistence)
        graph = {
            "graph_id": "g_local_001",
            "nodes": [{"id": "n1", "kind": "point", "geometry": {"type": "Point", "coordinates": [0, 0]}}],
            "edges": [],
            "metadata": {"dossier_id": "D_LOCAL"},
        }
        compile_result = compiler.compile({"graph": graph, "dossier_id": "D_LOCAL"})
        judge_result = judge.judge({"graph": graph, "dossier_id": "D_LOCAL"})

        compile_ref = ArtifactRef.model_validate(compile_result["artifact_ref"])
        judge_ref = ArtifactRef.model_validate(judge_result["artifact_ref"])
        assert "compiled" in compile_result["reason_codes"]
        assert "judged" in judge_result["reason_codes"]
        assert Path(compile_ref.artifact_path).exists()
        assert Path(judge_ref.artifact_path).exists()


def test_feature_graph_bundler_tool_persists_bundle_artifact_ref() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fg_persistence = FeatureGraphPersistenceService(
            root=root / "dossiers_data" / "artifacts" / "feature_graphs",
            state_dir=root / "dossiers_data" / "state",
        )
        bundler = FeatureGraphBundlerTool(persistence=fg_persistence)
        graph = {
            "graph_id": "g_bundle_001",
            "nodes": [{"id": "n1", "kind": "point", "geometry": {"type": "Point", "coordinates": [0, 0]}}],
            "edges": [],
            "metadata": {"dossier_id": "D_BUNDLE"},
        }
        bundle_result = bundler.bundle({"graph": graph, "dossier_id": "D_BUNDLE"})
        bundle_ref = ArtifactRef.model_validate(bundle_result["artifact_ref"])
        assert bundle_result["reason_codes"] == ["bundled"]
        assert Path(bundle_ref.artifact_path).exists()


class _FakeRetrievalEngine:
    def __init__(self, debug: dict[str, object]) -> None:
        self._debug = debug

    def search(self, query: str, *, filters=None, limit: int = 10, lanes=None) -> RetrievalResult:
        del query, filters, limit, lanes
        return RetrievalResult(query="q", cards=[], debug=self._debug)


def test_retrieval_tool_maps_semantic_worker_reason_codes() -> None:
    debug = {"lane_debug": {"hybrid_semantic": {"per_lane_debug": {"semantic": {"reason": "semantic_worker_in_backoff"}}}}}
    tool = RetrievalEvidenceTool(engine=_FakeRetrievalEngine(debug=debug))  # type: ignore[arg-type]
    result = tool.retrieve_evidence(
        {
            "query": "find anchor",
            "routing": {"lanes": ["hybrid_semantic"], "view": "everything"},
            "options": {"limit": 5},
            "dossier_id": "D_RET",
        }
    )

    artifact_ref = ArtifactRef.model_validate(result["artifact_ref"])
    assert result["reason_codes"] == ["semantic_worker_in_backoff"]
    assert Path(artifact_ref.artifact_path).exists()
