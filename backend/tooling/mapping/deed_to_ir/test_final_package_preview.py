"""Tests for deed-to-IR final package preview prepare/publish/hydrate flows."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from tooling.mapping.deed_to_ir.artifact_hydration import hydrate_artifact_refs
from tooling.mapping.deed_to_ir.final_package_preview_persistence import prepare_deed_to_ir_final_package
from tooling.mapping.deed_to_ir.final_package_preview_projection import (
    render_final_package_preview_timeline_lines,
    render_final_package_validation_timeline_lines,
)
from tooling.mapping.deed_to_ir.ir_mapping_submission import submit_ir_for_mapping
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.output_persistence import publish_deed_to_ir_output
from tooling.mapping.deed_to_ir.preview_refs import PREVIEW_REV_PREFIX


def _services(tmp: str):
    from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

    root = Path(tmp) / "artifacts"
    state = Path(tmp) / "state"
    fg_root = root / "feature_graphs"
    persistence = FeatureGraphPersistenceService(root=fg_root, state_dir=state)
    return persistence


def _mappable_graph() -> FeatureGraph:
    return FeatureGraph(
        graph_id="example_scope_graph",
        nodes=[
            FeatureNode(
                id="pob",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["pob"],
                    params={
                        "courses": [
                            {"bearing": 90.0, "distance": 100.0},
                            {"bearing": 0.0, "distance": 50.0},
                        ]
                    },
                ),
            ),
            FeatureNode(
                id="parcel",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["traverse"]),
            ),
        ],
        edges=[],
    )


def _context() -> dict:
    return {
        "transcription_id": "tx_preview",
        "workspace_id": "ws_preview",
        "run_id": None,
        "transcript_edit_source_revision_ref": "transcript_edit:output",
        "resolution_state_ref": "transcript_edit:resolution_state:fixture-001",
    }


def _patch_deed_root(monkeypatch, tmp: str) -> None:
    def _deed_root(dossier_id=None):
        base = Path(tmp) / "artifacts" / "deed_to_ir"
        return base if dossier_id is None else base / str(dossier_id)

    monkeypatch.setattr("tooling.mapping.deed_to_ir.paths.dossiers_deed_to_ir_artifacts_root", _deed_root)


def _prepare_mapping(tmp: str):
    persistence = _services(tmp)
    saved = save_ir_artifact(
        dossier_id="d-preview",
        feature_graph=_mappable_graph().model_dump(mode="json"),
        artifact_id="ir_preview",
        persistence=persistence,
    )
    submitted = submit_ir_for_mapping(
        dossier_id="d-preview",
        ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
        persistence=persistence,
    )
    return persistence, saved["outputs"]["ir_artifact_ref"], submitted["outputs"]["mapping_artifact_ref"]


def _valid_rows() -> dict:
    from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS

    return {
        "scope_results": [{"scope_id": "example_scope_1", "status": "handoffable"}],
        "closure_dimensions": [
            {"dimension_id": dimension_id, "status": "partial"}
            for dimension_id in sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
        ],
        "notes": [
            {
                "note_id": "preview_note",
                "summary": "Example preview note.",
                "basis_refs": [],
            }
        ],
    }


def test_prepare_preview_happy_path_derives_artifact_refs(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
        )

        assert result["executed"] is True
        outputs = result["outputs"]
        assert outputs["publish_ready_candidate"] is True
        assert outputs["final_package_preview_revision_ref"].startswith(PREVIEW_REV_PREFIX)
        assert outputs["recommended_publish_request"]["final_package_preview_ref"] == outputs[
            "final_package_preview_revision_ref"
        ]
        assert outputs["ir_artifact_ref"] == ir_ref
        assert outputs["mapping_artifact_ref"] == mapping_ref
        assert outputs["compile_artifact_ref"].startswith("feature_graph:compile:")
        assert outputs["judge_artifact_ref"].startswith("feature_graph:judge:")
        assert outputs["geometry_ref"].startswith("artifact://")
        assert outputs["control_render_ref"].startswith("artifact://")
        assert outputs["clean_render_ref"].startswith("artifact://")
        assert "review_summary" in outputs
        assert "compile_gap_count" in outputs["review_summary"]


def test_prepare_expected_ir_mismatch_refuses_and_persists_nothing(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref="feature_graph:ir:wrong_ir",
            persistence=persistence,
            **ctx,
            **_valid_rows(),
        )

        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "mapping_ir_lineage_mismatch"
        assert result["refusal"]["retryable"] is True
        preview_dir = (
            Path(tmp) / "artifacts" / "deed_to_ir" / "d-preview" / ctx["transcription_id"] / ctx["workspace_id"]
        ) / "final_package_preview"
        assert not preview_dir.exists() or not any(preview_dir.glob("rev_*.json"))


def test_prepare_invalid_rows_return_validation_errors_and_persist_nothing(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            scope_results="not-a-list",
            **ctx,
        )

        assert result["executed"] is False
        assert result["refusal"]["retryable"] is True
        assert result["outputs"]["validation_errors"]
        preview_dir = (
            Path(tmp) / "artifacts" / "deed_to_ir" / "d-preview" / ctx["transcription_id"] / ctx["workspace_id"]
        ) / "final_package_preview"
        assert not preview_dir.exists() or not any(preview_dir.glob("rev_*.json"))


def test_publish_from_preview_writes_output_and_pointers(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        prepared = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
        )
        preview_ref = prepared["outputs"]["final_package_preview_revision_ref"]

        published = publish_deed_to_ir_output(
            dossier_id="d-preview",
            final_package_preview_ref=preview_ref,
            persistence=persistence,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            transcript_edit_source_revision_ref=ctx["transcript_edit_source_revision_ref"],
            resolution_state_ref=ctx["resolution_state_ref"],
        )

        assert published["executed"] is True
        assert published["outputs"]["output_ref"] == "deed_to_ir:output"
        assert published["outputs"]["ir_artifact_ref"] == ir_ref
        output_dir = (
            Path(tmp) / "artifacts" / "deed_to_ir" / "d-preview" / ctx["transcription_id"] / ctx["workspace_id"] / "output"
        )
        assert (output_dir / "latest.json").is_file()
        assert any(output_dir.glob("rev_*.json"))


def test_publish_from_preview_rejects_missing_preview(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _, _ = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-preview",
            final_package_preview_ref="deed_to_ir:final_package_preview:rev:0099",
            persistence=persistence,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            transcript_edit_source_revision_ref=ctx["transcript_edit_source_revision_ref"],
            resolution_state_ref=ctx["resolution_state_ref"],
        )

        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "final_package_preview_not_found"


def test_publish_from_preview_rejects_row_mutation(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        prepared = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
        )
        preview_ref = prepared["outputs"]["final_package_preview_revision_ref"]

        result = publish_deed_to_ir_output(
            dossier_id="d-preview",
            final_package_preview_ref=preview_ref,
            scope_results=[{"scope_id": "mutated", "status": "blocked"}],
            persistence=persistence,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            transcript_edit_source_revision_ref=ctx["transcript_edit_source_revision_ref"],
            resolution_state_ref=ctx["resolution_state_ref"],
        )

        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "final_package_preview_row_mutation_forbidden"


def test_publish_from_preview_rejects_stale_preview_after_mapping_identity_drift(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        prepared = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
        )
        preview_ref = prepared["outputs"]["final_package_preview_revision_ref"]

        preview_path = (
            Path(tmp)
            / "artifacts"
            / "deed_to_ir"
            / "d-preview"
            / ctx["transcription_id"]
            / ctx["workspace_id"]
            / "final_package_preview"
            / "rev_0001.json"
        )
        raw = json.loads(preview_path.read_text(encoding="utf-8"))
        raw["selected_artifacts"]["ir_artifact_ref"] = "feature_graph:ir:stale_ir_ref"
        preview_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

        result = publish_deed_to_ir_output(
            dossier_id="d-preview",
            final_package_preview_ref=preview_ref,
            persistence=persistence,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            transcript_edit_source_revision_ref=ctx["transcript_edit_source_revision_ref"],
            resolution_state_ref=ctx["resolution_state_ref"],
        )

        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "final_package_preview_stale"


def test_preview_hydration_returns_bounded_summaries(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        prepared = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
        )
        preview_ref = prepared["outputs"]["final_package_preview_revision_ref"]

        hydrated = hydrate_artifact_refs(
            dossier_id="d-preview",
            ref_ids=[preview_ref],
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            persistence=persistence,
        )

        row = hydrated["outputs"]["results"][0]
        assert row["artifact_type"] == "deed_to_ir_final_package_preview"
        assert row["publish_ready_candidate"] is True
        assert row["recommended_publish_request"]["final_package_preview_ref"] == preview_ref
        assert row["selected_artifacts"]["ir_artifact_ref"] == ir_ref
        assert row["scope_summaries"]
        assert row["review_summary"] is not None
        dumped = json.dumps(hydrated)
        assert "\\\\" not in dumped
        assert ".png" not in dumped or "artifact://" in dumped


def test_timeline_renders_final_package_preview() -> None:
    preview = {
        "final_package_preview_revision_ref": "deed_to_ir:final_package_preview:rev:0001",
        "selected_artifacts": {
            "ir_artifact_ref": "feature_graph:ir:example_scope_v1",
            "mapping_artifact_ref": "feature_graph:mapping:mapping_example_scope_ab12cd34",
        },
        "scope_summaries": [
            {"scope_id": "example_scope_1", "status": "handoffable"},
            {"scope_id": "example_scope_2", "status": "blocked"},
        ],
        "external_dependency_count": 1,
        "closure_dimension_statuses": [
            {"dimension_id": "layer_1_deed_meaning_to_ir_fidelity", "status": "closed"},
        ],
        "publish_ready_candidate": True,
    }
    lines = render_final_package_preview_timeline_lines(preview)
    body = "\n".join(lines)
    assert "Final package preview:" in body
    assert "preview_ref:" in body
    assert "publish_ready_candidate: true" in body
    assert "example_scope_1=handoffable" in body


def test_direct_publish_still_works_for_backward_compatibility(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
        )

        assert result["executed"] is True
        assert result["outputs"]["output_revision_ref"].startswith("deed_to_ir:output:rev:")


def test_prepare_accepts_optional_scope_and_closure_title(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        rows = _valid_rows()
        rows["scope_results"] = [
            {
                "scope_id": "example_scope_1",
                "status": "handoffable",
                "title": "Example scope label",
            }
        ]
        rows["closure_dimensions"] = [
            {
                "dimension_id": dimension_id,
                "status": "partial",
                **(
                    {"title": "Handoff posture"}
                    if dimension_id == "layer_4_map_handoffability_scoped_completion"
                    else {}
                ),
            }
            for dimension_id in sorted(
                __import__(
                    "domains.mapping.deed_to_ir.payloads.published_output",
                    fromlist=["ALLOWED_CLOSURE_DIMENSION_IDS"],
                ).ALLOWED_CLOSURE_DIMENSION_IDS
            )
        ]

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **rows,
        )

        assert result["executed"] is True


def test_preview_model_rejects_oversized_scope_results_on_reload() -> None:
    from domains.mapping.deed_to_ir.payloads.final_package_preview import DeedToIrFinalPackagePreview
    from domains.mapping.deed_to_ir.payloads.published_output import MAX_SCOPE_RESULTS
    from pydantic import ValidationError

    payload = {
        "schema_version": "1.0",
        "source": {"transcript_edit_source_revision_ref": "transcript_edit:output"},
        "selected_artifacts": {
            "ir_artifact_ref": "feature_graph:ir:example",
            "compile_artifact_ref": "feature_graph:compile:example",
            "judge_artifact_ref": "feature_graph:judge:example",
            "mapping_artifact_ref": "feature_graph:mapping:example",
            "geometry_ref": "artifact://dossiers/feature_graphs/d-example/mappings/example/geometry.geojson",
            "clean_render_ref": "artifact://dossiers/feature_graphs/d-example/mappings/example/clean.png",
            "control_render_ref": "artifact://dossiers/feature_graphs/d-example/mappings/example/control.png",
        },
        "scope_results": [{"scope_id": f"scope_{index}", "status": "mapped"} for index in range(MAX_SCOPE_RESULTS + 1)],
        "external_dependencies": [],
        "closure_dimensions": [],
        "notes": [],
        "mechanical_review_summary": {
            "compile_gap_count": 0,
            "judge_finding_count": 0,
            "rendered_feature_count": 1,
            "skipped_feature_count": 0,
            "coordinate_space": "local",
        },
        "lineage_summary": {
            "current_ir_artifact_ref": "feature_graph:ir:example",
            "lineage_mismatch": False,
        },
        "publish_ready_candidate": True,
    }

    try:
        DeedToIrFinalPackagePreview.model_validate(payload)
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


def test_prepare_preview_pointer_failure_rolls_back_revision(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        original_write = __import__(
            "tooling.mapping.deed_to_ir.persistence_io",
            fromlist=["atomic_write_json"],
        ).atomic_write_json
        write_count = {"n": 0}

        def _fail_on_pointer_write(path, payload):
            write_count["n"] += 1
            if write_count["n"] == 2:
                raise OSError("preview_pointer_write_failed")
            return original_write(path, payload)

        monkeypatch.setattr(
            "tooling.mapping.deed_to_ir.final_package_preview_persistence.atomic_write_json",
            _fail_on_pointer_write,
        )

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
        )

        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "preview_pointer_write_failed"
        preview_dir = (
            Path(tmp)
            / "artifacts"
            / "deed_to_ir"
            / "d-preview"
            / ctx["transcription_id"]
            / ctx["workspace_id"]
            / "final_package_preview"
        )
        assert not any(preview_dir.glob("rev_*.json"))
