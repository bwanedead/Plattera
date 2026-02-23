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
    DeedSpanIndexUpserterTool,
    DraftIRFilesystemProposer,
    FeatureGraphBundlerTool,
    FeatureGraphCompilerTool,
    FeatureGraphJudgeTool,
    RetrievalEvidenceTool,
    TextSpanOpenerTool,
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
            ref = proposer.draft_ir(
                {
                    "dossier_id": "D_DRAFT",
                    "deed_text_artifact_ref": "artifacts/deed/draft_seed.json",
                }
            )

            payload = json.loads(Path(ref.artifact_path).read_text(encoding="utf-8"))
            assert payload["artifact_type"] == "ir_draft_stub"
            assert payload["dossier_id"] == "D_DRAFT"
            assert "graph" in payload
            assert str(payload["graph"].get("graph_id", "")).startswith("graph_draft_")
            assert payload["source_artifact_ref"]["artifact_path"] == "artifacts/deed/draft_seed.json"
        finally:
            legacy_paths.dossiers_root = original_legacy_dossiers_root  # type: ignore[assignment]


def test_draft_ir_proposer_uses_inline_graph_when_provided() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fg_persistence = FeatureGraphPersistenceService(
            root=root / "dossiers_data" / "artifacts" / "feature_graphs",
            state_dir=root / "dossiers_data" / "state",
        )
        proposer = DraftIRFilesystemProposer(persistence=fg_persistence)
        inline_graph = {
            "graph_id": "inline_1",
            "nodes": [{"id": "start", "kind": "point", "geometry": {"type": "Point", "coordinates": [0.0, 0.0]}}],
            "edges": [],
            "metadata": {"source": "unit-test", "dossier_id": "D_DRAFT"},
        }
        result = proposer.draft_ir({"dossier_id": "D_DRAFT", "graph": inline_graph})
        artifact_ref = ArtifactRef.model_validate(result["artifact_ref"])
        payload = json.loads(Path(artifact_ref.artifact_path).read_text(encoding="utf-8"))
        assert payload["artifact_type"] == "ir"
        assert payload["graph"]["graph_id"] == "inline_1"
        assert len(payload["graph"]["nodes"]) == 1
        latest_pointer = root / "dossiers_data" / "artifacts" / "feature_graphs" / "D_DRAFT" / "latest_ir.json"
        assert latest_pointer.exists()


def test_draft_ir_invalid_inline_graph_returns_repairable_refusal_and_does_not_update_latest_pointer() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fg_persistence = FeatureGraphPersistenceService(
            root=root / "dossiers_data" / "artifacts" / "feature_graphs",
            state_dir=root / "dossiers_data" / "state",
        )
        proposer = DraftIRFilesystemProposer(persistence=fg_persistence)
        invalid_graph = {
            "graph_id": "broken",
            "nodes": [{"id": "n1"}],  # missing kind
            "edges": [],
            "metadata": {"dossier_id": "D_BAD"},
        }
        result = proposer.draft_ir({"dossier_id": "D_BAD", "graph": invalid_graph})

        assert "draft_ir_graph_validation_failed" in result["reason_codes"]
        assert result["artifact_ref"] is None
        assert result["kernel_refusal"]["reason_code"] == "draft_ir_graph_validation_failed"
        rejected_ref = ArtifactRef.model_validate(result["rejected_graph_artifact_ref"])
        assert Path(rejected_ref.artifact_path).exists()
        assert isinstance(result["rejected_graph_summary"], dict)
        latest_pointer = root / "dossiers_data" / "artifacts" / "feature_graphs" / "D_BAD" / "latest_ir.json"
        assert not latest_pointer.exists()


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


def test_span_index_upsert_and_open_text_spans_returns_bounded_verbatim_text() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_legacy_dossiers_root = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            deed_text = (
                "Preamble text. BEGINNING AT the northeast corner of Lot 1; "
                "thence South 100 feet; thence West 50 feet; POINT OF BEGINNING. Closing text."
            )
            deed_ref = ArtifactRef(
                artifact_path=str(
                    (root / "dossiers_data" / "artifacts" / "agent_kernel" / "manual_deed.json")
                )
            )
            Path(deed_ref.artifact_path).parent.mkdir(parents=True, exist_ok=True)
            Path(deed_ref.artifact_path).write_text(
                json.dumps({"artifact_type": "deed_text", "dossier_id": "D_SPAN", "text": deed_text}),
                encoding="utf-8",
            )
            fp = {
                "sha256_12": __import__("hashlib").sha256(deed_text.encode("utf-8")).hexdigest()[:12],
                "length_chars": len(deed_text),
            }
            upserter = DeedSpanIndexUpserterTool()
            upsert = upserter.upsert_deed_span_index(
                {
                    "dossier_id": "D_SPAN",
                    "deed_text_artifact_ref": deed_ref.model_dump(mode="json"),
                    "deed_fingerprint": fp,
                    "upserts": [
                        {
                            "span_id": "calls_01",
                            "kind": "metes_bounds_calls",
                            "labels": ["calls"],
                            "status": "proposed",
                            "start_char": deed_text.index("BEGINNING AT"),
                            "end_char": deed_text.index("POINT OF BEGINNING") + len("POINT OF BEGINNING"),
                            "agent_intent": {"intended_verbatim_text": "BEGINNING AT ... POINT OF BEGINNING"},
                        }
                    ],
                }
            )
            index_ref = ArtifactRef.model_validate(upsert["artifact_ref"])
            assert "deed_span_index_saved" in upsert["reason_codes"]
            assert Path(index_ref.artifact_path).exists()

            opener = TextSpanOpenerTool()
            opened = opener.open_text_spans(
                {
                    "deed_text_artifact_ref": deed_ref.model_dump(mode="json"),
                    "deed_span_index_ref": index_ref.model_dump(mode="json"),
                    "span_ids": ["calls_01"],
                    "max_chars_per_span": 200,
                    "max_total_chars": 400,
                    "include_context_chars": 0,
                }
            )
            assert opened["reason_codes"] == ["spans_opened"]
            spans = opened["spans"]
            assert isinstance(spans, list) and len(spans) == 1
            assert "BEGINNING AT" in spans[0]["text"]
            assert "POINT OF BEGINNING" in spans[0]["text"]
            assert spans[0]["fingerprint_ok"] is True
        finally:
            legacy_paths.dossiers_root = original_legacy_dossiers_root  # type: ignore[assignment]


def test_open_text_spans_invalid_range_and_fingerprint_mismatch_refuse() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_legacy_dossiers_root = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            deed_text = "Short deed text for span testing."
            deed_path = root / "dossiers_data" / "artifacts" / "agent_kernel" / "deed.json"
            deed_path.parent.mkdir(parents=True, exist_ok=True)
            deed_path.write_text(json.dumps({"artifact_type": "deed_text", "text": deed_text}), encoding="utf-8")
            deed_ref = ArtifactRef(artifact_path=str(deed_path))

            opener = TextSpanOpenerTool()
            invalid = opener.open_text_spans(
                {
                    "deed_text_artifact_ref": deed_ref.model_dump(mode="json"),
                    "spans": [{"start_char": 10, "end_char": 5}],
                }
            )
            assert invalid["kernel_refusal"]["reason_code"] == "open_text_spans_invalid_range"

            bad_index_path = root / "dossiers_data" / "artifacts" / "agent_kernel" / "bad_index.json"
            bad_index_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "deed_span_index",
                        "deed_fingerprint": {"sha256_12": "deadbeefdead", "length_chars": 999},
                        "spans": [{"span_id": "s1", "start_char": 0, "end_char": 5}],
                    }
                ),
                encoding="utf-8",
            )
            mismatch = opener.open_text_spans(
                {
                    "deed_text_artifact_ref": deed_ref.model_dump(mode="json"),
                    "deed_span_index_ref": {"artifact_path": str(bad_index_path)},
                    "span_ids": ["s1"],
                }
            )
            assert mismatch["kernel_refusal"]["reason_code"] == "open_text_spans_fingerprint_mismatch"
        finally:
            legacy_paths.dossiers_root = original_legacy_dossiers_root  # type: ignore[assignment]


def test_open_text_spans_anchors_happy_not_found_and_ambiguous() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_legacy_dossiers_root = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            deed_text = (
                "Recital. BEGINNING AT stone marker A; thence east 10 feet; POINT OF BEGINNING. "
                "Other text. BEGINNING AT stone marker B; thence west 20 feet; POINT OF BEGINNING."
            )
            deed_path = root / "dossiers_data" / "artifacts" / "agent_kernel" / "deed_anchor.json"
            deed_path.parent.mkdir(parents=True, exist_ok=True)
            deed_path.write_text(json.dumps({"artifact_type": "deed_text", "text": deed_text}), encoding="utf-8")
            deed_ref = ArtifactRef(artifact_path=str(deed_path))
            opener = TextSpanOpenerTool()

            ok = opener.open_text_spans(
                {
                    "deed_text_artifact_ref": deed_ref.model_dump(mode="json"),
                    "anchors": [
                        {
                            "span_id": "calls_01",
                            "start_anchor": "BEGINNING AT stone marker A",
                            "end_anchor": "POINT OF BEGINNING",
                        }
                    ],
                    "include_context_chars": 0,
                }
            )
            assert ok["reason_codes"] == ["spans_opened"]
            assert "stone marker A" in ok["spans"][0]["text"]
            assert "stone marker B" not in ok["spans"][0]["text"]
            assert ok["spans"][0]["start_char"] < ok["spans"][0]["end_char"]

            not_found = opener.open_text_spans(
                {
                    "deed_text_artifact_ref": deed_ref.model_dump(mode="json"),
                    "anchors": [{"start_anchor": "NO SUCH START", "end_anchor": "POINT OF BEGINNING"}],
                }
            )
            assert not_found["kernel_refusal"]["reason_code"] == "open_text_spans_anchor_not_found"

            ambiguous = opener.open_text_spans(
                {
                    "deed_text_artifact_ref": deed_ref.model_dump(mode="json"),
                    "anchors": [{"start_anchor": "BEGINNING AT", "end_anchor": "POINT OF BEGINNING"}],
                }
            )
            assert ambiguous["kernel_refusal"]["reason_code"] == "open_text_spans_anchor_ambiguous"
            assert isinstance(ambiguous.get("candidates"), list)
            assert ambiguous["candidates"], "expected candidate previews"
        finally:
            legacy_paths.dossiers_root = original_legacy_dossiers_root  # type: ignore[assignment]
