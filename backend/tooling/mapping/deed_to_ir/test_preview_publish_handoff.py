"""Regression tests for preview handoff projection and hydrate-next (internal prepare outputs)."""

from __future__ import annotations

from domains.mapping.deed_to_ir.domain_pack import build_deed_to_ir_domain_pack
from domains.mapping.deed_to_ir.execution.tool_specs import build_deed_to_ir_tool_specs
from harness.audit.human_timeline import _render_hydration_lane, _render_tool_result
from harness.runtime.orchestration.hydrate_next import (
    enrich_hydrate_next_resolution_errors,
    resolve_hydrate_next_refs,
)
from tooling.mapping.deed_to_ir.final_package_preview_projection import (
    PREPARE_PREVIEW_OUTPUT_TOP_LEVEL_KEYS,
    render_final_package_preview_tool_output,
)

_REVISION_REF = "deed_to_ir:final_package_preview:rev:0001"


def _preview_outputs() -> dict:
    return {
        "final_package_preview_ref": "deed_to_ir:final_package_preview",
        "final_package_preview_revision_ref": _REVISION_REF,
        "working_preview_ref": _REVISION_REF,
        "publish_ready_candidate": True,
        "scope_summaries": [{"scope_id": "example_scope", "status": "mapped"}],
        "recommended_publish_request": {"final_package_preview_ref": _REVISION_REF},
        "preview_ready_summary": {
            "ready_for_publish_candidate": True,
            "expected_next": "publish_deed_to_ir_output",
            "hydrate_preview_optional": True,
            "state_alignment_optional": True,
        },
    }


def test_prepare_preview_output_aliases_are_stable():
    for key in PREPARE_PREVIEW_OUTPUT_TOP_LEVEL_KEYS:
        assert key in _preview_outputs()


def test_timeline_renders_preview_ready_expected_next():
    lines = render_final_package_preview_tool_output(_preview_outputs(), indent="  ")
    body = "\n".join(lines)
    assert "preview_ready_summary:" in body
    assert "expected_next: publish_deed_to_ir_output" in body
    assert "hydrate_preview_optional: true" in body
    assert f"recommended_publish_request: final_package_preview_ref={_REVISION_REF}" in body


def test_agent_surface_exposes_finalize_not_prepare_or_publish():
    ids = [spec.tool_id for spec in build_deed_to_ir_tool_specs()]
    assert "finalize_current_deed_to_ir_output" in ids
    assert "prepare_deed_to_ir_final_package" not in ids
    assert "publish_deed_to_ir_output" not in ids


def test_procedural_guidance_teaches_compact_finalizer_not_preview_launchpad():
    block = next(
        b
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert block.version == "v36"
    text = block.text
    assert "finalize_current_deed_to_ir_output" in text
    assert "prepare_deed_to_ir_final_package" not in text
    assert "publish_deed_to_ir_output" not in text
    assert "publish launchpad" not in text.lower()
    assert "recommended_publish_request" not in text


def test_derived_ref_id_after_preview_emits_advisory_hint():
    outputs = _preview_outputs()
    _, errors = resolve_hydrate_next_refs(
        ["@this.result.derived_ref_id"],
        tool_result={"outputs": outputs, "artifact_refs": [_REVISION_REF]},
    )
    enriched = enrich_hydrate_next_resolution_errors(
        errors,
        source_action_type="prepare_deed_to_ir_final_package",
        tool_outputs=outputs,
    )
    assert enriched
    assert enriched[0]["reason_code"] == "hydrate_next_placeholder_not_supported"
    assert "working_preview_ref" in enriched[0]["hint"]
    assert enriched[0]["valid_replacements"] == [
        "@this.result.working_preview_ref",
        "@this.result.final_package_preview_revision_ref",
    ]
    assert enriched[0]["hydration_optional"] is True


def test_hydration_lane_renders_placeholder_hint():
    lane = {
        "requested_refs": ["@this.result.derived_ref_id"],
        "resolved_refs": [],
        "errors": [
            {
                "requested_ref": "@this.result.derived_ref_id",
                "reason_code": "hydrate_next_placeholder_not_supported",
                "hint": (
                    "@this.result.derived_ref_id is not emitted by prepare_deed_to_ir_final_package. "
                    "Use @this.result.working_preview_ref or @this.result.final_package_preview_revision_ref."
                ),
                "valid_replacements": [
                    "@this.result.working_preview_ref",
                    "@this.result.final_package_preview_revision_ref",
                ],
                "hydration_optional": True,
            }
        ],
    }
    body = "\n".join(_render_hydration_lane(lane, indent="  ", title="agent_requested_hydration"))
    assert "hydrate_next_placeholder_not_supported" in body
    assert "working_preview_ref" in body
    assert "valid_replacements:" in body
    assert "hydration_optional: true" in body


def test_working_preview_ref_placeholder_resolves():
    outputs = _preview_outputs()
    resolved, errors = resolve_hydrate_next_refs(
        ["@this.result.working_preview_ref"],
        tool_result={"outputs": outputs, "artifact_refs": [_REVISION_REF]},
    )
    assert errors == []
    assert resolved == [_REVISION_REF]


def test_timeline_tool_result_renders_preview_ready_summary_from_prepare():
    turn = {
        "tool_result_raw": {
            "execution_state": "executed",
            "outputs": _preview_outputs(),
        },
        "tool_request": {"action_type": "prepare_deed_to_ir_final_package"},
        "parsed_action_plan": {"action_type": "prepare_deed_to_ir_final_package"},
    }
    body = "\n".join(_render_tool_result(turn))
    assert "preview_ready_summary:" in body
    assert "expected_next: publish_deed_to_ir_output" in body
