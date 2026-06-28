"""Tests for deed-to-IR published output persistence and publication."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from tooling.mapping.deed_to_ir.artifact_hydration import hydrate_artifact_refs
from tooling.mapping.deed_to_ir.ir_mapping_submission import submit_ir_for_mapping
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.output_persistence import publish_deed_to_ir_output


def _services(tmp: str):
    from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

    root = Path(tmp) / "artifacts"
    state = Path(tmp) / "state"
    fg_root = root / "feature_graphs"
    persistence = FeatureGraphPersistenceService(root=fg_root, state_dir=state)
    return persistence


def _mappable_graph() -> FeatureGraph:
    return FeatureGraph(
        graph_id="parcel_publish",
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


def _publish_context() -> dict:
    return {
        "transcription_id": "tx_publish",
        "workspace_id": "ws_publish",
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
        dossier_id="d-pub",
        feature_graph=_mappable_graph().model_dump(mode="json"),
        artifact_id="ir_publish",
        persistence=persistence,
    )
    submitted = submit_ir_for_mapping(
        dossier_id="d-pub",
        ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
        persistence=persistence,
    )
    return persistence, submitted["outputs"]["mapping_artifact_ref"]


def _prepare_stale_mapping_lineage(tmp: str):
    """IR v0 mapped, then patched to v1 and remapped — returns stale and current mapping refs."""
    persistence = _services(tmp)
    graph = _mappable_graph().model_dump(mode="json")
    graph["graph_id"] = "example_scope_graph"
    v0 = save_ir_artifact(
        dossier_id="d-pub",
        feature_graph=graph,
        persistence=persistence,
    )
    v0_ref = v0["outputs"]["ir_artifact_ref"]
    mapping_v0 = submit_ir_for_mapping(
        dossier_id="d-pub",
        ir_artifact_ref=v0_ref,
        persistence=persistence,
    )
    v1 = save_ir_artifact(
        dossier_id="d-pub",
        feature_graph=graph,
        base_draft_ref=v0_ref,
        persistence=persistence,
    )
    v1_ref = v1["outputs"]["ir_artifact_ref"]
    mapping_v1 = submit_ir_for_mapping(
        dossier_id="d-pub",
        ir_artifact_ref=v1_ref,
        persistence=persistence,
    )
    return (
        persistence,
        mapping_v0["outputs"]["mapping_artifact_ref"],
        mapping_v1["outputs"]["mapping_artifact_ref"],
        v0_ref,
        v1_ref,
    )


def test_valid_package_publishes_and_hydrates(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[{"scope_id": "parcel_1", "status": "mapped"}],
            notes=[
                {
                    "note_id": "handoff_note",
                    "summary": "Example structured publish note.",
                    "basis_refs": [],
                }
            ],
            closure_dimensions=[
                {
                    "dimension_id": "layer_4_map_handoffability_scoped_completion",
                    "status": "partial",
                    "summary": "Primary parcel mapped.",
                }
            ],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is True
        assert result["outputs"]["note_count"] == 1
        assert result["outputs"]["output_ref"] == "deed_to_ir:output"
        assert result["artifact_refs"][0] == "deed_to_ir:output"

        hydrated = hydrate_artifact_refs(
            dossier_id="d-pub",
            ref_ids=["deed_to_ir:output"],
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            persistence=persistence,
        )
        row = hydrated["outputs"]["results"][0]
        assert row["artifact_type"] == "deed_to_ir_output"
        assert row["selected_artifacts"]["mapping_artifact_ref"] == mapping_ref
        dumped = json.dumps(result)
        assert tmp not in dumped
        assert "b64" not in dumped


def test_repeated_publication_creates_append_only_revisions(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        first = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[{"scope_id": "parcel_1", "status": "mapped"}],
            **ctx,
            persistence=persistence,
        )
        second = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[{"scope_id": "parcel_1", "status": "blocked"}],
            **ctx,
            persistence=persistence,
        )
        assert first["outputs"]["output_revision_ref"] != second["outputs"]["output_revision_ref"]
        output_dir = Path(tmp) / "artifacts" / "deed_to_ir" / "d-pub" / "tx_publish" / "ws_publish" / "output"
        assert (output_dir / "rev_0001.json").exists()
        assert (output_dir / "rev_0002.json").exists()
        assert (output_dir / "latest.json").exists()


def test_partial_blocked_scopes_publish_honestly(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[
                {"scope_id": "parcel_1", "status": "mapped"},
                {"scope_id": "parcel_2", "status": "blocked", "summary": "External dependency pending."},
            ],
            external_dependencies=[
                {
                    "dependency_id": "adj_1",
                    "affected_scope": "parcel_2",
                    "description": "Adjoiner deed unavailable",
                    "status": "pending",
                    "available_refs": [],
                }
            ],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is True
        assert result["outputs"]["scope_status_counts"]["mapped"] == 1
        assert result["outputs"]["scope_status_counts"]["blocked"] == 1
        assert result["outputs"]["external_dependency_count"] == 1


def test_publish_refuses_missing_mapping(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence = _services(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref="feature_graph:mapping:missing_map",
            scope_results=[],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "mapping_artifact_not_found"


def test_publish_refuses_wrong_type_ref(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref="feature_graph:ir:ir_publish",
            scope_results=[],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "mapping_artifact_ref_invalid"


def test_publish_refuses_without_workspace_identity(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            transcription_id="tx_publish",
            workspace_id=None,
            run_id=None,
            mapping_artifact_ref=mapping_ref,
            transcript_edit_source_revision_ref="transcript_edit:output",
            resolution_state_ref=None,
            scope_results=[],
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "workspace_identity_required"


def test_mark_final_artifact_sets_ir_and_mapping_pointers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        mapping_id = mapping_ref.split(":", 2)[2]
        persistence.mark_final_artifact(dossier_id="d-pub", artifact_type="ir", artifact_id="ir_publish")
        persistence.mark_final_artifact(dossier_id="d-pub", artifact_type="mapping", artifact_id=mapping_id)
        final_ir = json.loads(
            (Path(tmp) / "artifacts" / "feature_graphs" / "d-pub" / "final_ir.json").read_text(encoding="utf-8")
        )
        final_mapping = json.loads(
            (Path(tmp) / "artifacts" / "feature_graphs" / "d-pub" / "final_mapping.json").read_text(
                encoding="utf-8"
            )
        )
        assert final_ir["artifact_id"] == "ir_publish"
        assert final_mapping["artifact_id"] == mapping_id


def test_publish_refuses_unknown_scope_fields(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[{"scope_id": "parcel_1", "status": "mapped", "unexpected": True}],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "publish_payload_validation_failed"
        assert result["refusal"]["retryable"] is True
        assert result["refusal"]["blocked_by_invariant"] is False
        errors = result["outputs"]["validation_errors"]
        assert any(err["path"] == "scope_results[0].unexpected" for err in errors)
        assert any(err["code"] == "extra_forbidden" for err in errors)


def test_publish_refuses_external_dependency_shape_errors(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            external_dependencies=[
                {
                    "dependency_id": "missing_continuation_source",
                    "status": "missing",
                    "summary": "Wrong field used instead of description.",
                }
            ],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["retryable"] is True
        errors = result["outputs"]["validation_errors"]
        paths = {err["path"] for err in errors}
        assert "external_dependencies[0].affected_scope" in paths
        assert "external_dependencies[0].description" in paths
        assert "external_dependencies[0].summary" in paths


def test_publish_refuses_string_notes(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            notes=["plain string note"],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["retryable"] is True
        assert result["outputs"]["validation_errors"]
        assert result["outputs"]["validation_errors"][0]["path"] == "notes[0]"


def test_publish_refuses_object_notes(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            notes={"note_id": "handoff_note", "summary": "Structured note sent as object, not array."},
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["retryable"] is True
        errors = result["outputs"]["validation_errors"]
        assert any(err["path"] == "notes" and err["code"] == "invalid" for err in errors)


def test_publish_refuses_object_external_dependencies(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            external_dependencies={
                "dependency_id": "missing_continuation_source",
                "affected_scope": "example_scope",
                "description": "Sent as object instead of array.",
                "status": "missing",
            },
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["retryable"] is True
        errors = result["outputs"]["validation_errors"]
        assert any(
            err["path"] == "external_dependencies" and err["code"] == "invalid"
            for err in errors
        )


def test_publish_validation_errors_are_capped_at_24(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[{"scope_id": f"scope_{index}"} for index in range(30)],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        errors = result["outputs"]["validation_errors"]
        assert len(errors) == 24
        assert errors[-1]["code"] == "validation_errors_truncated"


def test_publish_validation_failure_does_not_persist_output(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            external_dependencies=[{"dependency_id": "dep_only"}],
            **ctx,
            persistence=persistence,
        )
        output_dir = Path(tmp) / "artifacts" / "deed_to_ir" / "d-pub" / "tx_publish" / "ws_publish"
        assert not any(output_dir.glob("rev_*.json")) if output_dir.is_dir() else True


def test_publish_succeeds_when_expected_ir_matches_mapping_source(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _mapping_v0, mapping_v1, _v0_ref, v1_ref = _prepare_stale_mapping_lineage(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_v1,
            expected_ir_artifact_ref=v1_ref,
            scope_results=[{"scope_id": "example_scope_1", "status": "handoffable"}],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is True
        assert result["outputs"]["ir_artifact_ref"] == v1_ref


def test_publish_refuses_stale_mapping_when_expected_ir_mismatch(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_v0, _mapping_v1, v0_ref, v1_ref = _prepare_stale_mapping_lineage(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_v0,
            expected_ir_artifact_ref=v1_ref,
            scope_results=[{"scope_id": "example_scope_1", "status": "handoffable"}],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "mapping_ir_lineage_mismatch"
        assert result["refusal"]["retryable"] is True
        assert result["refusal"]["blocked_by_invariant"] is False
        outputs = result["outputs"]
        assert outputs["expected_ir_artifact_ref"] == v1_ref
        assert outputs["actual_ir_artifact_ref"] == v0_ref
        assert "repair_hint" in outputs
        output_dir = Path(tmp) / "artifacts" / "deed_to_ir" / "d-pub" / "tx_publish" / "ws_publish"
        assert not any(output_dir.glob("rev_*.json")) if output_dir.is_dir() else True


def test_publish_omitted_expected_ir_remains_backward_compatible(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_v0, _mapping_v1, v0_ref, _v1_ref = _prepare_stale_mapping_lineage(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_v0,
            scope_results=[{"scope_id": "example_scope_1", "status": "handoffable"}],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is True
        assert result["outputs"]["ir_artifact_ref"] == v0_ref


def test_publish_scope_results_basis_refs_persist_and_hydrate(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)
        ir_ref = "feature_graph:ir:ir_publish"
        basis = [ir_ref, mapping_ref]

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[
                {
                    "scope_id": "example_scope_1",
                    "status": "handoffable",
                    "basis_refs": basis,
                }
            ],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is True

        hydrated = hydrate_artifact_refs(
            dossier_id="d-pub",
            ref_ids=[result["outputs"]["output_ref"]],
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            persistence=persistence,
        )
        row = hydrated["outputs"]["results"][0]
        scope_row = row["scope_results"][0]
        assert scope_row["basis_refs"] == basis


def test_publish_refuses_invalid_scope_basis_refs(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[
                {
                    "scope_id": "example_scope_1",
                    "status": "handoffable",
                    "basis_refs": [""],
                }
            ],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["retryable"] is True
        errors = result["outputs"]["validation_errors"]
        assert any(
            err["path"] == "scope_results[0].basis_refs[0]" and err["code"] == "value_error"
            for err in errors
        ) or any("basis_refs" in err["path"] for err in errors)


def test_publish_refuses_scope_results_cap_exceeded(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[
                {"scope_id": f"scope_{i}", "status": "mapped"}
                for i in range(33)
            ],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "publish_payload_validation_failed"
        assert result["refusal"]["retryable"] is True
        assert any(err["path"] == "scope_results" and err["code"] == "cap_exceeded" for err in result["outputs"]["validation_errors"])


def test_publish_returns_closure_dimension_statuses_in_outputs(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[{"scope_id": "parcel_1", "status": "mapped"}],
            closure_dimensions=[
                {
                    "dimension_id": "layer_4_map_handoffability_scoped_completion",
                    "status": "partial",
                }
            ],
            **ctx,
            persistence=persistence,
        )
        statuses = result["outputs"]["closure_dimension_statuses"]
        assert statuses == [
            {
                "dimension_id": "layer_4_map_handoffability_scoped_completion",
                "status": "partial",
            }
        ]


def test_publish_refuses_stale_lineage_package(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        mapping_id = mapping_ref.split(":", 2)[2]
        mapping_raw = persistence.get_artifact("d-pub", mapping_id)
        assert mapping_raw is not None
        compile_id = mapping_raw["compile_artifact_id"]
        compile_raw = persistence.get_artifact("d-pub", compile_id)
        assert compile_raw is not None
        compile_raw["metadata"]["parent_artifact_ids"] = ["ir_stale_parent"]
        persistence._atomic_write(
            persistence._artifact_file_path("d-pub", compile_id),
            compile_raw,
        )
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "compile_ir_parent_missing"


def test_publish_refuses_wrong_lineage_artifact_type(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        mapping_id = mapping_ref.split(":", 2)[2]
        mapping_raw = persistence.get_artifact("d-pub", mapping_id)
        assert mapping_raw is not None
        compile_id = mapping_raw["compile_artifact_id"]
        compile_raw = persistence.get_artifact("d-pub", compile_id)
        assert compile_raw is not None
        compile_raw["artifact_type"] = "ir"
        persistence._atomic_write(
            persistence._artifact_file_path("d-pub", compile_id),
            compile_raw,
        )
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "compile_artifact_type_mismatch"


def test_publish_refuses_graph_id_mismatch(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        mapping_id = mapping_ref.split(":", 2)[2]
        mapping_raw = persistence.get_artifact("d-pub", mapping_id)
        assert mapping_raw is not None
        compile_id = mapping_raw["compile_artifact_id"]
        compile_raw = persistence.get_artifact("d-pub", compile_id)
        assert compile_raw is not None
        compile_raw["graph_id"] = "different_graph"
        persistence._atomic_write(
            persistence._artifact_file_path("d-pub", compile_id),
            compile_raw,
        )
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "compile_graph_id_mismatch"


def test_publish_refuses_missing_sidecar(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        mapping_id = mapping_ref.split(":", 2)[2]
        sidecar = (
            Path(tmp) / "artifacts" / "feature_graphs" / "d-pub" / "mappings" / mapping_id / "clean.png"
        )
        sidecar.unlink()
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "mapping_sidecar_missing"


def test_publish_refuses_cross_dossier_mapping(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-other",
            mapping_artifact_ref=mapping_ref,
            scope_results=[],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "mapping_artifact_not_found"


def test_publish_accepts_long_generated_sidecar_refs(monkeypatch) -> None:
    long_dossier = "d_" + ("x" * 80)
    with tempfile.TemporaryDirectory() as tmp:
        persistence = _services(tmp)
        saved = save_ir_artifact(
            dossier_id=long_dossier,
            feature_graph=_mappable_graph().model_dump(mode="json"),
            artifact_id="ir_publish",
            persistence=persistence,
        )
        submitted = submit_ir_for_mapping(
            dossier_id=long_dossier,
            ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
            persistence=persistence,
        )
        mapping_ref = submitted["outputs"]["mapping_artifact_ref"]
        mapping_id = mapping_ref.split(":", 2)[2]
        mapping_raw = persistence.get_artifact(long_dossier, mapping_id)
        assert mapping_raw is not None
        geometry_ref = mapping_raw["geometry"]["ref"]
        assert len(geometry_ref) > 128
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id=long_dossier,
            mapping_artifact_ref=mapping_ref,
            scope_results=[{"scope_id": "parcel_1", "status": "mapped"}],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is True
        assert result["outputs"]["geometry_ref"] == geometry_ref


def test_publish_refuses_invalid_scope_path(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            transcription_id="../evil",
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            transcript_edit_source_revision_ref=ctx["transcript_edit_source_revision_ref"],
            resolution_state_ref=ctx["resolution_state_ref"],
            mapping_artifact_ref=mapping_ref,
            scope_results=[],
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "invalid_scope_path"


def test_publish_refuses_when_workspace_lock_held(monkeypatch) -> None:
    import threading

    from tooling.mapping.deed_to_ir.output_persistence import _workspace_publish_lock
    from tooling.mapping.deed_to_ir.paths import deed_to_ir_output_dir

    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)
        output_dir = deed_to_ir_output_dir("d-pub", ctx["transcription_id"], ctx["workspace_id"])
        started = threading.Event()
        release = threading.Event()

        def _hold_lock() -> None:
            with _workspace_publish_lock(output_dir):
                started.set()
                release.wait(timeout=5)

        holder = threading.Thread(target=_hold_lock, daemon=True)
        holder.start()
        assert started.wait(timeout=5)

        try:
            result = publish_deed_to_ir_output(
                dossier_id="d-pub",
                mapping_artifact_ref=mapping_ref,
                scope_results=[],
                **ctx,
                persistence=persistence,
            )
        finally:
            release.set()
            holder.join(timeout=5)

        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "publication_in_progress"


def test_publish_refuses_overwriting_existing_revision(monkeypatch) -> None:
    from tooling.mapping.deed_to_ir.paths import deed_to_ir_output_dir

    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)
        output_dir = deed_to_ir_output_dir("d-pub", ctx["transcription_id"], ctx["workspace_id"])
        output_dir.mkdir(parents=True, exist_ok=True)
        existing = output_dir / "rev_0001.json"
        existing.write_text('{"schema_version":"1.0","marker":"keep"}', encoding="utf-8")

        monkeypatch.setattr(
            "tooling.mapping.deed_to_ir.output_persistence._next_revision_digits",
            lambda *, output_dir: "0001",
        )

        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "output_revision_exists"
        assert existing.read_text(encoding="utf-8") == '{"schema_version":"1.0","marker":"keep"}'


def test_publish_final_pointer_failure_does_not_advance_latest(monkeypatch) -> None:
    from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_mapping(tmp)
        ctx = _publish_context()
        _patch_deed_root(monkeypatch, tmp)

        first = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[{"scope_id": "parcel_1", "status": "mapped"}],
            **ctx,
            persistence=persistence,
        )
        assert first["executed"] is True
        latest_path = (
            Path(tmp)
            / "artifacts"
            / "deed_to_ir"
            / "d-pub"
            / ctx["transcription_id"]
            / ctx["workspace_id"]
            / "output"
            / "latest.json"
        )
        rev_0001_path = latest_path.parent / "rev_0001.json"
        final_ir_path = Path(tmp) / "artifacts" / "feature_graphs" / "d-pub" / "final_ir.json"
        final_mapping_path = Path(tmp) / "artifacts" / "feature_graphs" / "d-pub" / "final_mapping.json"
        first_latest = json.loads(latest_path.read_text(encoding="utf-8"))
        first_final_ir = final_ir_path.read_bytes()
        first_final_mapping = final_mapping_path.read_bytes()
        first_rev_0001 = rev_0001_path.read_bytes()

        original_write = FeatureGraphPersistenceService._write_pointer
        final_pointer_names = frozenset(
            {"final_ir.json", "final_bundle.json", "final_mapping.json"}
        )
        transaction_write = {"n": 0}

        def _reset_transaction_counter(self, **kwargs):
            transaction_write["n"] = 0
            return original_mark_final_artifacts(self, **kwargs)

        original_mark_final_artifacts = FeatureGraphPersistenceService.mark_final_artifacts

        def _fail_on_second_pointer_in_transaction(self, **kwargs):
            if kwargs.get("pointer_filename") in final_pointer_names:
                transaction_write["n"] += 1
                if transaction_write["n"] == 2:
                    raise ValueError("final_pointer_write_failed")
            return original_write(self, **kwargs)

        monkeypatch.setattr(
            FeatureGraphPersistenceService,
            "mark_final_artifacts",
            _reset_transaction_counter,
        )
        monkeypatch.setattr(
            FeatureGraphPersistenceService,
            "_write_pointer",
            _fail_on_second_pointer_in_transaction,
        )

        second = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[{"scope_id": "parcel_1", "status": "blocked"}],
            **ctx,
            persistence=persistence,
        )
        assert second["executed"] is False
        assert second["refusal"]["reason_code"] == "final_pointer_write_failed"
        second_latest = json.loads(latest_path.read_text(encoding="utf-8"))
        assert second_latest == first_latest
        assert final_ir_path.read_bytes() == first_final_ir
        assert final_mapping_path.read_bytes() == first_final_mapping
        assert rev_0001_path.read_bytes() == first_rev_0001
        assert (latest_path.parent / "rev_0002.json").exists() is False
