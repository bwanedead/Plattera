"""Tests for correction posture detector, contract card, and prepare preview gate."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS, UpstreamCorrectionRow
from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode, OpExpr
from feature_graph.provenance import ProvenanceAttachment, SourceEntityLink
from harness.audit.human_timeline import _render_tool_result
from tooling.mapping.deed_to_ir.artifact_hydration import hydrate_artifact_refs
from tooling.mapping.deed_to_ir.correction_contract_card import (
    CORRECTION_CONTRACT_REF,
    build_correction_contract_card,
    build_upstream_correction_row_template_from_delta,
    agent_facing_example_contains_practice_deed_tokens,
    upstream_correction_row_contract_fields,
)
from tooling.mapping.deed_to_ir.correction_posture import (
    REASON_IR_DIFFERS,
    detect_correction_posture,
    render_correction_posture_timeline_lines,
    render_upstream_corrections_required_timeline_lines,
    upstream_corrections_required_refusal,
)
from tooling.mapping.deed_to_ir.final_package_preview_persistence import prepare_deed_to_ir_final_package
from tooling.mapping.deed_to_ir.final_package_preview_projection import (
    render_final_package_preview_tool_output,
    render_final_package_validation_timeline_lines,
)
from tooling.mapping.deed_to_ir.ir_mapping_submission import submit_ir_for_mapping
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.test_correction_lane_advisory import (
    _SOURCE_REPAIR_RESOLUTION,
    _run24_suspicious_rows,
)
from tooling.mapping.deed_to_ir.test_final_package_preview import (
    _context,
    _patch_deed_root,
    _valid_rows,
)

from tooling.mapping.deed_to_ir.test_upstream_corrections import _sample_upstream_correction
_PRACTICE_CORRECT_DISTANCE = 518.0
_PRACTICE_CORRUPTED_DISTANCE = 618.0


def _closure_dimensions() -> list[dict]:
    return [
        {"dimension_id": dimension_id, "status": "partial"}
        for dimension_id in sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
    ]


def _source_repair_graph(
    *,
    leg2_distance: float,
    leg2_distance_raw: str | None = None,
) -> FeatureGraph:
    course2: dict = {"bearing": 267.583333, "distance": leg2_distance}
    if leg2_distance_raw is not None:
        course2["distance_raw"] = leg2_distance_raw
    courses = [
        {"bearing": 68.5, "distance": 542.0},
        course2,
        {"bearing": 176.0, "distance": 180.0},
    ]
    return FeatureGraph(
        graph_id="source_repair_scope",
        nodes=[
            FeatureNode(
                id="pob",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="parcel_1_traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["pob"],
                    params={"courses": courses},
                ),
                provenance=ProvenanceAttachment(
                    source_entity_links=[
                        SourceEntityLink(
                            entity_id="p1_call2_bearing",
                            entity_type="bearing",
                            source_ref="transcript_edit:resolution_state:fixture",
                        ),
                    ]
                ),
            ),
        ],
        edges=[],
    )


def _prepare_source_repair_mapping(tmp: str, *, leg2_distance: float):
    from tooling.mapping.deed_to_ir.test_final_package_preview import _services

    persistence = _services(tmp)
    saved = save_ir_artifact(
        dossier_id="d-preview",
        feature_graph=_source_repair_graph(leg2_distance=leg2_distance).model_dump(mode="json"),
        artifact_id="ir_source_repair",
        persistence=persistence,
    )
    submitted = submit_ir_for_mapping(
        dossier_id="d-preview",
        ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
        persistence=persistence,
    )
    return persistence, saved["outputs"]["ir_artifact_ref"], submitted["outputs"]["mapping_artifact_ref"]


def _resolution_snapshot() -> dict:
    return json.loads(_SOURCE_REPAIR_RESOLUTION.read_text(encoding="utf-8"))


def test_detector_inactive_for_matching_ir_and_inherited() -> None:
    graph = _source_repair_graph(leg2_distance=_PRACTICE_CORRUPTED_DISTANCE)
    posture = detect_correction_posture(
        resolution_state_snapshot=_resolution_snapshot(),
        ir_graph=graph,
        ir_artifact_ref="feature_graph:ir:example",
    )
    assert posture["active"] is False
    assert posture["candidate_deltas"] == []


def test_detector_active_for_run25_shaped_delta() -> None:
    graph = _source_repair_graph(leg2_distance=_PRACTICE_CORRECT_DISTANCE)
    posture = detect_correction_posture(
        resolution_state_snapshot=_resolution_snapshot(),
        ir_graph=graph,
        ir_artifact_ref="feature_graph:ir:example",
    )
    assert posture["active"] is True
    assert REASON_IR_DIFFERS in posture["reason_codes"]
    assert "contract_ref" not in posture
    deltas = posture["candidate_deltas"]
    assert len(deltas) >= 1
    distance_delta = next(row for row in deltas if row.get("target_entity_id") == "p1_call2_distance")
    assert distance_delta["value_kind"] == "distance"
    assert "618" in str(distance_delta["inherited_value"])
    assert "518" in str(distance_delta["ir_value"])
    assert distance_delta["selected_ir_value"] == _PRACTICE_CORRECT_DISTANCE


def test_detector_uses_typed_ir_value_when_raw_provenance_lags() -> None:
    """Live failure shape: typed distance repaired to 518 while distance_raw still says 618 feet."""
    graph = _source_repair_graph(
        leg2_distance=_PRACTICE_CORRECT_DISTANCE,
        leg2_distance_raw="618 feet",
    )
    posture = detect_correction_posture(
        resolution_state_snapshot=_resolution_snapshot(),
        ir_graph=graph,
        ir_artifact_ref="feature_graph:ir:example",
    )
    assert posture["active"] is True
    distance_delta = next(
        row for row in posture["candidate_deltas"] if row.get("target_entity_id") == "p1_call2_distance"
    )
    assert distance_delta["selected_ir_value"] == _PRACTICE_CORRECT_DISTANCE
    assert distance_delta["selected_ir_display_value"] == "518 feet"
    assert distance_delta["ir_value"] == "518 feet"
    assert "618" in str(distance_delta["inherited_value"])
    assert distance_delta.get("ir_raw_provenance") == "618 feet"
    # Agent-facing selected IR must never present the stale raw as the selected value.
    assert distance_delta["ir_value"] != "618 feet"
    assert "618" not in str(distance_delta["selected_ir_display_value"])

    template = build_upstream_correction_row_template_from_delta(distance_delta)
    assert "518" in str(template["corrected_value"])
    assert "618" not in str(template["corrected_value"])

    timeline = "\n".join(render_correction_posture_timeline_lines(posture))
    assert "selected_ir=518 feet" in timeline
    assert "typed=518" in timeline
    assert "618 → 618" not in timeline
    assert "inherited=618" in timeline or "618 feet" in timeline


def test_contract_card_uses_generic_example_only() -> None:
    card = build_correction_contract_card()
    dumped = json.dumps(card)
    assert "618" not in dumped
    assert "518" not in dumped
    assert card["example_row"]["upstream_value"] == "430 feet"
    assert card["example_row"]["corrected_value"] == "410 feet"


def test_contract_card_row_fields_match_pydantic_model() -> None:
    derived = upstream_correction_row_contract_fields()
    required_from_model = [
        name for name, field in UpstreamCorrectionRow.model_fields.items() if field.is_required()
    ]
    optional_from_model = [
        name for name, field in UpstreamCorrectionRow.model_fields.items() if not field.is_required()
    ]
    assert derived["required_row_fields"] == required_from_model
    assert derived["optional_row_fields"] == optional_from_model

    card = build_correction_contract_card()
    assert card["required_row_fields"] == required_from_model
    assert card["optional_row_fields"] == optional_from_model
    assert set(card["required_row_fields"]) == {
        "correction_id",
        "posture",
        "resolution_used_by_ir",
        "recommended_action",
        "basis_refs",
        "rationale",
    }
    assert set(card["optional_row_fields"]) == {
        "title",
        "target_entity_id",
        "target_entity_type",
        "upstream_value",
        "corrected_value",
    }


def test_hydrate_correction_contract_ref() -> None:
    hydrated = hydrate_artifact_refs(
        dossier_id="d-preview",
        ref_ids=[CORRECTION_CONTRACT_REF],
    )
    row = hydrated["outputs"]["results"][0]
    assert row["ref_id"] == CORRECTION_CONTRACT_REF
    assert row["artifact_type"] == "deed_to_ir_correction_contract"
    assert "required_row_fields" in row
    assert "optional_row_fields" in row


def test_hydrate_correction_contract_rejects_typo_ref() -> None:
    hydrated = hydrate_artifact_refs(
        dossier_id="d-preview",
        ref_ids=["deed_to_ir:correction_contract_bad"],
    )
    assert hydrated["outputs"]["results"] == []
    errors = hydrated["outputs"]["errors"]
    assert len(errors) == 1
    assert errors[0]["ref_id"] == "deed_to_ir:correction_contract_bad"


def test_prepare_run25_shape_refuses_with_empty_corrections(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_source_repair_mapping(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
        )
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        rows = _valid_rows()
        rows["upstream_corrections"] = []
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **rows,
        )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "upstream_corrections_required"
    assert result["refusal"]["retryable"] is True
    outputs = result["outputs"]
    assert outputs["correction_posture"]["active"] is True
    assert outputs["correction_contract_ref"] == CORRECTION_CONTRACT_REF
    assert outputs["correction_contract_card"]["contract_ref"] == CORRECTION_CONTRACT_REF
    assert "retry_package_shell" in outputs["repair_hint"]
    assert isinstance(outputs.get("candidate_deltas"), list)
    assert outputs.get("forbidden_fields")
    assert outputs.get("field_mapping_hints")
    assert outputs.get("valid_postures") == [
        "suspected",
        "confirmed_from_source",
        "needs_hitl",
    ]
    assert "confirmed" not in outputs["valid_postures"]
    shell = outputs.get("retry_package_shell")
    assert isinstance(shell, dict)
    assert shell.get("mapping_artifact_ref") == mapping_ref
    assert shell.get("expected_ir_artifact_ref") == ir_ref
    assert shell.get("missing_section") == "upstream_corrections"
    assert isinstance(shell.get("scope_results"), list) and shell["scope_results"]
    templates = outputs.get("upstream_corrections_template")
    assert isinstance(templates, list) and templates
    template = templates[0]
    assert template["posture"] == "confirmed_from_source"
    assert "rationale" in template
    assert "upstream_value" in template
    assert "corrected_value" in template
    assert "inherited_value" not in template
    assert "ir_value" not in template
    assert "summary" not in template
    UpstreamCorrectionRow.model_validate(
        {
            **template,
            "correction_id": "test_correction_row",
            "rationale": "Source evidence supports the corrected value used by the final IR.",
        }
    )


def test_prepare_run25_shape_succeeds_with_correction_row(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_source_repair_mapping(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
        )
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        rows = _valid_rows()
        rows["upstream_corrections"] = [
            _sample_upstream_correction(
                target_entity_id="p1_call2_distance",
                upstream_value="618 feet",
                corrected_value="518 feet",
            )
        ]
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **rows,
        )
    assert result["executed"] is True
    assert result["outputs"].get("upstream_correction_count") == 1
    assert "correction_posture" not in result["outputs"]


def test_prepare_refusal_does_not_persist_preview(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_source_repair_mapping(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
        )
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **_valid_rows(),
            upstream_corrections=[],
        )
        assert result["executed"] is False
        success = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **_valid_rows(),
            upstream_corrections=[_sample_upstream_correction()],
        )
        assert success["executed"] is True
        assert success["outputs"]["final_package_preview_revision_ref"].endswith(":rev:0001")


def test_submit_includes_correction_posture_lane(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, _ = _prepare_source_repair_mapping(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
        )
        submitted = submit_ir_for_mapping(
            dossier_id="d-preview",
            ir_artifact_ref=ir_ref,
            persistence=persistence,
            resolution_state_snapshot=_resolution_snapshot(),
        )
    posture = submitted["outputs"]["mapping_review"].get("correction_posture")
    assert isinstance(posture, dict)
    assert posture.get("active") is True
    assert posture.get("candidate_delta_count", 0) >= 1


def test_timeline_renders_correction_posture_and_refusal() -> None:
    graph = _source_repair_graph(leg2_distance=_PRACTICE_CORRECT_DISTANCE)
    posture = detect_correction_posture(
        resolution_state_snapshot=_resolution_snapshot(),
        ir_graph=graph,
        ir_artifact_ref="feature_graph:ir:example",
    )
    lines = render_correction_posture_timeline_lines(posture)
    body = "\n".join(lines)
    assert "correction_posture:" in body
    assert "ir_value_differs_from_inherited_operand" in body
    assert "contract_ref" not in body

    refusal = upstream_corrections_required_refusal(
        correction_posture=posture,
        retry_package_shell={
            "mapping_artifact_ref": "feature_graph:mapping:example",
            "expected_ir_artifact_ref": "feature_graph:ir:example",
            "missing_section": "upstream_corrections",
            "scope_results": [{"scope_id": "s1", "status": "complete"}],
        },
    )
    refusal_outputs = refusal["outputs"]
    timeline_lines = render_upstream_corrections_required_timeline_lines(refusal_outputs)
    timeline_body = "\n".join(timeline_lines)
    assert "upstream_corrections_required:" in timeline_body
    assert "missing_section: upstream_corrections" in timeline_body
    assert "template_rows:" in timeline_body
    assert "forbidden_fields:" in timeline_body
    assert "retry_package_shell: present" in timeline_body
    assert "618 feet" not in timeline_body
    assert "518 feet" not in timeline_body

    validation_lines = render_final_package_validation_timeline_lines(refusal_outputs)
    assert "upstream_corrections_required:" in "\n".join(validation_lines)

    tool_lines = render_final_package_preview_tool_output(refusal_outputs)
    tool_body = "\n".join(tool_lines)
    assert "upstream_corrections_required:" in tool_body

    turn = {
        "tool_result_raw": {
            "execution_state": "refused",
            "outputs": refusal_outputs,
        }
    }
    rendered = "\n".join(_render_tool_result(turn))
    assert "upstream_corrections_required:" in rendered


def test_generic_contract_example_avoids_practice_deed_tokens() -> None:
    card = build_correction_contract_card()
    assert agent_facing_example_contains_practice_deed_tokens(card.get("example_row")) == []
    generic_template = build_upstream_correction_row_template_from_delta({})
    assert generic_template["upstream_value"] == "430 feet"
    assert generic_template["corrected_value"] == "410 feet"
    assert generic_template["target_entity_id"] == "example_call_2_distance"
    assert agent_facing_example_contains_practice_deed_tokens(generic_template) == []


def test_upstream_corrections_template_fields_match_model() -> None:
    template = build_upstream_correction_row_template_from_delta(
        {
            "target_entity_id": "p1_call2_distance",
            "inherited_value": "618 feet",
            "ir_value": "518 feet",
            "basis_refs": ["feature_graph:ir:example"],
        }
    )
    row = dict(template)
    row["correction_id"] = "practice_distance_correction"
    row["rationale"] = "Source image confirms 518 feet."
    validated = UpstreamCorrectionRow.model_validate(row)
    assert validated.upstream_value == "618 feet"
    assert validated.corrected_value == "518 feet"


def test_detector_does_not_author_upstream_correction_rows() -> None:
    graph = _source_repair_graph(leg2_distance=_PRACTICE_CORRECT_DISTANCE)
    posture = detect_correction_posture(
        resolution_state_snapshot=_resolution_snapshot(),
        ir_graph=graph,
        ir_artifact_ref="feature_graph:ir:example",
    )
    dumped = json.dumps(posture)
    assert "correction_id" not in dumped
    assert "upstream_corrections" not in dumped
    assert "recommended_action" not in dumped


def test_normal_prepare_without_snapshot_still_succeeds(monkeypatch) -> None:
    from tooling.mapping.deed_to_ir.test_final_package_preview import _prepare_mapping

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


def test_run24_advisory_still_non_blocking_without_snapshot(monkeypatch) -> None:
    from tooling.mapping.deed_to_ir.test_final_package_preview import _prepare_mapping

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
            **_run24_suspicious_rows(),
        )
    assert result["executed"] is True
    assert isinstance(result["outputs"].get("correction_lane_advisory"), dict)
