"""Tests for generic completion-anchor evaluation from domain closure policy."""

from __future__ import annotations

from dataclasses import asdict

from domains.mapping.deed_to_ir.semantics.closure import build_deed_to_ir_closure_policy
from harness.audit.human_timeline import _render_observability, _render_tool_result
from harness.runtime.orchestration.completion_anchor import (
    apply_completion_anchor_to_closure_readiness,
    evaluate_completion_anchor,
    is_posture_mirror_blocker,
)
from harness.runtime.orchestration.loop_health_summary import build_prompt_observability_summary
from harness.runtime.orchestration.test_loop_health_summary import _item, _mem
from tooling.mapping.deed_to_ir.publish_gate_feedback import build_final_output_summary

_PREVIEW_REF = "deed_to_ir:final_package_preview:rev:0001"
_MAPPING_B = "feature_graph:mapping:scope_b"
_MAPPING_A = "feature_graph:mapping:scope_a"


def _closure_policy_dict() -> dict:
    return asdict(build_deed_to_ir_closure_policy())


def _publish_result_record(
    *,
    turn: int = 5,
    mapping_ref: str = _MAPPING_B,
    preview_ref: str | None = _PREVIEW_REF,
) -> dict:
    outputs: dict = {
        "output_ref": "deed_to_ir:output",
        "output_revision_ref": "deed_to_ir:output:rev:0001",
        "mapping_artifact_ref": mapping_ref,
        "ir_artifact_ref": "feature_graph:ir:example_scope_v1",
        "final_output_summary": build_final_output_summary(publish_succeeded=True),
    }
    if preview_ref:
        outputs["final_package_preview_ref"] = preview_ref
    return {
        "kernel_turn_index": turn,
        "action_type": "finalize_current_deed_to_ir_output",
        "execution_state": "executed",
        "artifact_refs": [
            "deed_to_ir:output",
            "deed_to_ir:output:rev:0001",
            mapping_ref,
        ],
        "outputs_for_continuity": outputs,
    }


def _latest_refs(*, mapping_ref: str = _MAPPING_B, preview_ref: str = _PREVIEW_REF) -> dict[str, str]:
    return {
        "output": "deed_to_ir:output",
        "preview": preview_ref,
        "mapping_old": _MAPPING_A,
        "mapping": mapping_ref,
        "ir": "feature_graph:ir:example_scope_v1",
    }


def test_completion_anchor_satisfied_when_publish_and_refs_present():
    policy = _closure_policy_dict()
    anchor = evaluate_completion_anchor(
        closure_policy=policy,
        latest_refs=_latest_refs(),
        step_result_records=[_publish_result_record()],
    )
    assert anchor is not None
    assert anchor["satisfied"] is True
    assert "expected_next" not in anchor
    assert anchor["ready_for_completion_candidate"] is True
    assert anchor["mapping_ref"] == _MAPPING_B
    assert anchor["preview_ref"] == _PREVIEW_REF


def test_unsuccessful_finalize_does_not_satisfy_anchor():
    record = _publish_result_record()
    record["outputs_for_continuity"]["final_output_summary"] = {
        "ready_for_completion_candidate": False,
        "hydrate_output_ref_optional": False,
    }
    anchor = evaluate_completion_anchor(
        closure_policy=_closure_policy_dict(),
        latest_refs=_latest_refs(),
        step_result_records=[record],
    )
    assert anchor is not None
    assert anchor["satisfied"] is False
    assert "ready_for_completion_candidate_false" in anchor["missing_requirements"]


def test_completion_anchor_uses_publish_mapping_ref_when_multiple_exist():
    anchor = evaluate_completion_anchor(
        closure_policy=_closure_policy_dict(),
        latest_refs=_latest_refs(mapping_ref=_MAPPING_B),
        step_result_records=[_publish_result_record(mapping_ref=_MAPPING_B)],
    )
    assert anchor is not None
    assert anchor["satisfied"] is True
    assert anchor["mapping_ref"] == _MAPPING_B
    assert "mapping_lineage_mismatch" not in (anchor.get("missing_requirements") or [])


def test_completion_anchor_rejects_publish_mapping_ref_missing_from_latest_refs():
    anchor = evaluate_completion_anchor(
        closure_policy=_closure_policy_dict(),
        latest_refs={"mapping": _MAPPING_A, "preview": _PREVIEW_REF, "output": "deed_to_ir:output"},
        step_result_records=[_publish_result_record(mapping_ref=_MAPPING_B)],
    )
    assert anchor is not None
    assert anchor["satisfied"] is False
    assert "mapping_artifact_ref_not_in_latest_refs" in anchor["missing_requirements"]


def test_completion_anchor_requires_exact_preview_ref_from_publish():
    anchor = evaluate_completion_anchor(
        closure_policy=_closure_policy_dict(),
        latest_refs=_latest_refs(preview_ref="deed_to_ir:final_package_preview:rev:0099"),
        step_result_records=[_publish_result_record(preview_ref=_PREVIEW_REF)],
    )
    assert anchor is not None
    assert anchor["satisfied"] is False
    assert "preview_lineage_mismatch" in anchor["missing_requirements"]


def test_direct_publish_without_preview_ref_not_anchored():
    anchor = evaluate_completion_anchor(
        closure_policy=_closure_policy_dict(),
        latest_refs=_latest_refs(),
        step_result_records=[_publish_result_record(preview_ref=None)],
    )
    assert anchor is not None
    assert anchor["satisfied"] is False
    assert "published_preview_ref" in anchor["missing_requirements"]


def test_no_completion_anchor_without_domain_policy():
    anchor = evaluate_completion_anchor(
        closure_policy=None,
        latest_refs=_latest_refs(),
        step_result_records=[_publish_result_record()],
    )
    assert anchor is None


def test_posture_mirror_blockers_suppressed_when_anchor_satisfied():
    projection = {
        "complete_run_blockers": [
            "ready_to_close_false",
            "work_universe_not_audited:partial",
            "items_require_hitl:1",
        ],
        "publish_blockers": [],
    }
    policy = _closure_policy_dict()
    anchor = evaluate_completion_anchor(
        closure_policy=policy,
        latest_refs=_latest_refs(),
        step_result_records=[_publish_result_record()],
    )
    adjusted = apply_completion_anchor_to_closure_readiness(
        projection,
        anchor=anchor,
        closure_policy=policy,
    )
    assert adjusted["complete_run_blockers"] == ["items_require_hitl:1"]
    suppressed = adjusted["completion_anchor"]["completion_anchor_suppressed_flags"]
    assert suppressed[0]["flag"] == "complete_run_blockers_present"


def test_loop_health_suppresses_complete_run_blockers_present_after_publish_r16_shape():
    mem = _mem(
        ready_to_close=False,
        work_universe_posture="partial",
        step_result_records=[_publish_result_record()],
    )
    mem.continuity.latest_refs = _latest_refs()
    summary = build_prompt_observability_summary(
        mem,
        closure_policy=_closure_policy_dict(),
    )
    assert summary["completion_anchor"]["satisfied"] is True
    assert "complete_run_blockers_present" not in summary["mechanical_flags"]
    assert "completion_anchor_satisfied" in summary["mechanical_flags"]
    assert "expected_next:complete_run" not in summary["mechanical_flags"]
    assert "items_require_hitl" not in " ".join(summary["closure_readiness_projection"]["complete_run_blockers"])


def test_loop_health_keeps_real_blockers_when_anchor_not_satisfied():
    mem = _mem(
        ready_to_close=False,
        work_universe_posture="partial",
        step_result_records=[],
    )
    mem.continuity.latest_refs = {"mapping": _MAPPING_B}
    summary = build_prompt_observability_summary(mem, closure_policy=_closure_policy_dict())
    assert summary["completion_anchor"]["satisfied"] is False
    assert "complete_run_blockers_present" in summary["mechanical_flags"]


def test_loop_health_keeps_hitl_blocker_even_when_anchor_satisfied():
    policy = _closure_policy_dict() | {"hard_enforced": True, "enforce_on_complete": True}
    mem = _mem(
        ready_to_close=False,
        work_universe_posture="partial",
        requires_hitl=True,
        step_result_records=[_publish_result_record()],
        resolution_items=[
            _item("i1", status="open", requires_hitl=True),
        ],
    )
    mem.continuity.latest_refs = _latest_refs()
    summary = build_prompt_observability_summary(mem, closure_policy=policy)
    blockers = summary["closure_readiness_projection"]["complete_run_blockers"]
    assert any("items_require_hitl" in blocker or "closure_requires_hitl" in blocker for blocker in blockers)
    assert "complete_run_blocked:" in " ".join(summary["mechanical_flags"])


def test_timeline_renders_completion_anchor_from_observability():
    policy = _closure_policy_dict()
    turn = {
        "prompt_observability_summary": {
            "completion_anchor": evaluate_completion_anchor(
                closure_policy=policy,
                latest_refs=_latest_refs(),
                step_result_records=[_publish_result_record()],
            ),
            "mechanical_flags": ["completion_anchor_satisfied"],
        }
    }
    body = "\n".join(_render_observability(turn))
    assert "completion_anchor:" in body
    assert "expected_next: complete_run" not in body
    assert "deed_to_ir:output" in body


def test_timeline_finalize_result_renders_completion_anchor_without_complete_run():
    turn = {
        "tool_result_raw": {
            "execution_state": "executed",
            "outputs": {
                "output_ref": "deed_to_ir:output",
                "output_revision_ref": "deed_to_ir:output:rev:0001",
                "mapping_artifact_ref": _MAPPING_B,
                "final_output_summary": build_final_output_summary(publish_succeeded=True),
            },
        },
        "tool_request": {"action_type": "finalize_current_deed_to_ir_output"},
        "parsed_action_plan": {"action_type": "finalize_current_deed_to_ir_output"},
    }
    body = "\n".join(_render_tool_result(turn))
    assert "expected_next: complete_run" not in body
    assert "ready_for_completion_candidate: true" in body


def test_timeline_renders_closure_enforcement_blocked_finalize_gate():
    from harness.audit.human_timeline import _render_closure_enforcement_block

    turn = {
        "terminal_decision": "closure_enforcement_blocked",
        "closure_enforcement_block": {
            "blocked_action_id": "finalize_current_deed_to_ir_output",
            "closure_enforcement_reason_code": "work_universe_publish_not_audited",
            "publish_gate_category": "publish_posture_audit_gate",
            "preview_still_valid": True,
            "next_repair_action": "Patch posture, then retry finalize.",
        },
        "tool_request": {"action_type": "finalize_current_deed_to_ir_output"},
        "parsed_action_plan": {"action_type": "finalize_current_deed_to_ir_output"},
    }
    body = "\n".join(_render_closure_enforcement_block(turn))
    assert "Closure Enforcement Block" in body
    assert "finalize_current_deed_to_ir_output" in body
    assert "work_universe_publish_not_audited" in body
    assert "preview_still_valid: true" in body


def test_is_posture_mirror_blocker_classification():
    policy = build_deed_to_ir_closure_policy().completion_anchor
    assert policy is not None
    assert is_posture_mirror_blocker("ready_to_close_false", policy=policy)
    assert is_posture_mirror_blocker("work_universe_not_audited:partial", policy=policy)
    assert not is_posture_mirror_blocker("items_require_hitl:2", policy=policy)
    assert not is_posture_mirror_blocker("closure_requires_hitl", policy=policy)


def test_historical_publish_action_does_not_satisfy_anchor():
    historical_record = {
        "kernel_turn_index": 5,
        "action_type": "publish_deed_to_ir_output",
        "execution_state": "executed",
        "artifact_refs": [
            "deed_to_ir:output",
            "deed_to_ir:output:rev:0001",
            _MAPPING_B,
        ],
        "outputs_for_continuity": {
            "output_ref": "deed_to_ir:output",
            "output_revision_ref": "deed_to_ir:output:rev:0001",
            "mapping_artifact_ref": _MAPPING_B,
            "ir_artifact_ref": "feature_graph:ir:example_scope_v1",
            "final_package_preview_ref": _PREVIEW_REF,
            "final_output_summary": build_final_output_summary(publish_succeeded=True),
        },
    }
    anchor = evaluate_completion_anchor(
        closure_policy=_closure_policy_dict(),
        latest_refs=_latest_refs(),
        step_result_records=[historical_record],
    )
    assert anchor is not None
    assert anchor["satisfied"] is False


def test_domain_surface_preview_bypass_false_and_empty_prepare_ids():
    from domains.mapping.deed_to_ir import build_deed_to_ir_domain_pack

    payload = build_deed_to_ir_domain_pack().build_surface_payload()
    anchor_policy = payload["closure_policy"]["completion_anchor"]
    assert anchor_policy["preview_ready_publish_bypass"] is False
    assert anchor_policy["preview_prepare_action_ids"] == []
    assert anchor_policy["publish_action_ids"] == ["finalize_current_deed_to_ir_output"]
