"""Tests for deed-to-IR publish gate feedback and publish output summaries."""

from __future__ import annotations

import json
import tempfile

from tooling.mapping.deed_to_ir.output_persistence import publish_deed_to_ir_output
from tooling.mapping.deed_to_ir.publish_gate_feedback import (
    POSTURE_AUDIT_REPAIR_HINT,
    PUBLISH_GATE_POSTURE_AUDIT,
    PUBLISH_GATE_PREVIEW_PACKAGE_INVALID,
    build_closure_enforcement_block_feedback,
    build_publish_gate_feedback,
    classify_publish_gate_reason,
    render_closure_enforcement_blocked_timeline_lines,
    render_publish_gate_timeline_lines,
    render_publish_output_summary_timeline_lines,
)
from tooling.mapping.deed_to_ir.test_final_package_preview import (
    _context,
    _patch_deed_root,
    _prepare_mapping,
    _valid_rows,
)


def test_posture_audit_gate_does_not_imply_preview_invalidity() -> None:
    gate = build_publish_gate_feedback(reason_code="work_universe_publish_not_audited")
    assert gate["publish_gate_category"] == PUBLISH_GATE_POSTURE_AUDIT
    assert gate["preview_still_valid"] is True
    assert POSTURE_AUDIT_REPAIR_HINT in gate["repair_hint"]
    assert "same final_package_preview_ref" in gate["repair_hint"]


def test_closure_enforcement_blocked_timeline_shows_gate_reason() -> None:
    feedback = build_closure_enforcement_block_feedback(
        blocked_action_id="publish_deed_to_ir_output",
        reason_code="work_universe_publish_not_audited",
        preview_still_valid=True,
    )
    body = "\n".join(render_closure_enforcement_blocked_timeline_lines(feedback))
    assert "closure_enforcement_blocked:" in body
    assert "blocked_action_id: publish_deed_to_ir_output" in body
    assert "work_universe_publish_not_audited" in body
    assert "preview_still_valid: true" in body
    assert "next_repair_action:" in body


def test_preview_invalid_gate_classifies_validation_failures() -> None:
    assert (
        classify_publish_gate_reason("final_package_preview_not_ready")
        == PUBLISH_GATE_PREVIEW_PACKAGE_INVALID
    )
    assert (
        classify_publish_gate_reason("publish_payload_validation_failed")
        == PUBLISH_GATE_PREVIEW_PACKAGE_INVALID
    )


def test_publish_refusal_includes_publish_gate_feedback(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = publish_deed_to_ir_output(
            dossier_id="d-preview",
            final_package_preview_ref="deed_to_ir:final_package_preview:rev:0099",
            persistence=persistence,
            **ctx,
        )

        assert result["executed"] is False
        outputs = result["outputs"]
        assert outputs["publish_gate_category"] == PUBLISH_GATE_PREVIEW_PACKAGE_INVALID
        assert outputs["repair_hint"]


def test_successful_publish_outputs_final_output_summary(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        from tooling.mapping.deed_to_ir.final_package_preview_persistence import (
            prepare_deed_to_ir_final_package,
        )

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
            persistence=persistence,
            **ctx,
        )

        assert result["executed"] is True
        summary = result["outputs"]["final_output_summary"]
        assert summary["ready_for_completion_candidate"] is True
        assert summary["hydrate_output_ref_optional"] is True
        assert result["outputs"]["scope_result_count"] >= 1
        assert result["outputs"]["closure_dimension_count"] == 4


def test_timeline_renders_compact_publish_summary() -> None:
    outputs = {
        "output_ref": "deed_to_ir:output",
        "output_revision_ref": "deed_to_ir:output:rev:0001",
        "ir_artifact_ref": "feature_graph:ir:example_scope_v1",
        "mapping_artifact_ref": "feature_graph:mapping:mapping_example_scope_ab12cd34",
        "scope_result_count": 2,
        "scope_status_counts": {"handoffable": 1, "blocked": 1},
        "external_dependency_count": 1,
        "closure_dimension_count": 4,
        "closure_dimension_statuses": [
            {"dimension_id": "layer_1_deed_meaning_to_ir_fidelity", "status": "closed"},
        ],
        "final_output_summary": {
            "ready_for_completion_candidate": True,
            "hydrate_output_ref_optional": True,
        },
    }
    lines = render_publish_output_summary_timeline_lines(outputs)
    body = "\n".join(lines)
    assert "publish_output_summary:" in body
    assert "scope_status_counts: blocked=1, handoffable=1" in body
    assert "hydrate_output_ref_optional: true" in body


def test_timeline_renders_publish_gate_refusal() -> None:
    lines = render_publish_gate_timeline_lines(
        reason_code="work_universe_publish_not_audited",
        outputs=build_publish_gate_feedback(reason_code="work_universe_publish_not_audited"),
    )
    body = "\n".join(lines)
    assert "publish_gate:" in body
    assert "category: publish_posture_audit_gate" in body
    assert "preview_still_valid: true" in body
    assert "same final_package_preview_ref" in body


def test_publish_gate_timeline_has_no_row_values() -> None:
    lines = render_publish_gate_timeline_lines(
        reason_code="final_package_preview_not_ready",
        outputs={"error": {"message": "secret package row value"}},
    )
    dumped = json.dumps(lines)
    assert "secret package row value" not in dumped
