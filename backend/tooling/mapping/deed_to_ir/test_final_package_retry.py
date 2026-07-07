"""Tests for final package retry shell and combined validation/lineage refusals."""

from __future__ import annotations

import tempfile

from tooling.mapping.deed_to_ir.final_package_preview_persistence import prepare_deed_to_ir_final_package
from tooling.mapping.deed_to_ir.final_package_preview_projection import (
    render_final_package_preview_tool_output,
)
from tooling.mapping.deed_to_ir.final_package_retry_projection import (
    build_retry_package_shell,
    render_retry_package_shell_timeline_lines,
)
from tooling.mapping.deed_to_ir.ir_mapping_submission import submit_ir_for_mapping
from tooling.mapping.deed_to_ir.test_correction_posture import (
    _PRACTICE_CORRECT_DISTANCE,
    _prepare_source_repair_mapping,
    _resolution_snapshot,
)
from tooling.mapping.deed_to_ir.test_final_package_preview import (
    _context,
    _patch_deed_root,
    _prepare_mapping,
    _valid_rows,
)


def test_build_retry_package_shell_is_bounded_and_copyable() -> None:
    shell = build_retry_package_shell(
        mapping_artifact_ref="feature_graph:mapping:example",
        expected_ir_artifact_ref="feature_graph:ir:example",
        scope_results=[{"scope_id": "example_scope_1", "status": "handoffable"}],
        external_dependencies=[],
        closure_dimensions=[{"dimension_id": "layer_1_deed_meaning_to_ir_fidelity", "status": "partial"}],
        notes=[{"note_id": "n1", "summary": "note", "basis_refs": []}],
        correction_posture={
            "active": True,
            "candidate_deltas": [
                {
                    "target_entity_id": "example_call2_distance",
                    "value_kind": "distance",
                    "inherited_value": "410 feet",
                    "ir_value": "438 feet",
                }
            ],
        },
    )
    assert shell["mapping_artifact_ref"] == "feature_graph:mapping:example"
    assert shell["missing_section"] == "upstream_corrections"
    assert "correction_id" in shell["required_upstream_correction_fields"]
    assert "title" in shell["optional_upstream_correction_fields"]
    assert "correction_id" not in shell
    lines = render_retry_package_shell_timeline_lines(shell)
    assert "retry_package_shell:" in "\n".join(lines)


def test_prepare_combined_upstream_validation_and_lineage_mismatch(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        rows = _valid_rows()
        rows["upstream_corrections"] = [
            {
                "correction_id": "incomplete_correction",
                "resolution_used_by_ir": True,
                "basis_refs": ["feature_graph:ir:example"],
            }
        ]
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref="feature_graph:ir:stale_ir_ref",
            persistence=persistence,
            **ctx,
            **rows,
        )
    assert result["executed"] is False
    assert "mapping_ir_lineage_mismatch" in result.get("reason_codes", [])
    outputs = result["outputs"]
    validation_errors = outputs.get("validation_errors")
    assert isinstance(validation_errors, list)
    paths = {err.get("path") for err in validation_errors if isinstance(err, dict)}
    assert any(str(path or "").startswith("upstream_corrections[0]") for path in paths)
    assert outputs.get("lineage_mismatch", {}).get("expected_ir_artifact_ref") == "feature_graph:ir:stale_ir_ref"
    assert outputs.get("lineage_mismatch", {}).get("actual_ir_artifact_ref") == ir_ref


def test_timeline_renders_combined_refusal(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        rows = _valid_rows()
        rows["upstream_corrections"] = [{"correction_id": "bad", "resolution_used_by_ir": True}]
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref="feature_graph:ir:stale_ir_ref",
            persistence=persistence,
            **ctx,
            **rows,
        )
    lines = render_final_package_preview_tool_output(result.get("outputs"))
    body = "\n".join(lines)
    assert "final_package_validation:" in body or "validation_errors" in str(result.get("outputs"))


def test_submit_returns_lineage_lock(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_source_repair_mapping(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
        )
        submitted = submit_ir_for_mapping(
            dossier_id="d-preview",
            ir_artifact_ref=ir_ref,
            persistence=persistence,
            resolution_state_snapshot=_resolution_snapshot(),
        )
    lock = submitted["outputs"].get("lineage_lock")
    assert isinstance(lock, dict)
    assert lock.get("mapping_artifact_ref") == submitted["outputs"]["mapping_artifact_ref"]
    assert lock.get("source_ir_artifact_ref") == ir_ref
    assert lock.get("use_these_refs_for_next_preview") is True
    review_lock = submitted["outputs"]["mapping_review"].get("lineage_lock")
    assert review_lock == lock
