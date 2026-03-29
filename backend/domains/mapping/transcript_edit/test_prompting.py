from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domains.mapping.transcript_edit.prompting import (
    build_focus_resolver_system_message,
    build_focus_resolver_repair_user_message,
    build_focus_resolver_user_message,
    build_planner_system_message,
    build_planner_user_message,
    slim_execution_context_for_planner,
)


def test_focus_resolver_prompt_includes_external_context_injections_section() -> None:
    user_msg = build_focus_resolver_user_message(
        focus_packet={
            "decision_key": "range",
            "source_transcript_ref": "in-memory://source.json",
            "source_transcript_hash": "sha256:test",
            "external_context_injections": [
                {
                    "type": "human_resolution_ticket",
                    "ticket_id": "hitl_range_1_x",
                    "decision_key": "range",
                    "lifecycle_state": "answered_unintegrated",
                    "strength": "binding",
                    "payload": {"normalized_answer_summary": "Range 75 West"},
                }
            ],
        }
    )
    payload = json.loads(user_msg)
    assert isinstance(payload.get("external_context_injections"), list)
    assert len(payload["external_context_injections"]) == 1
    assert payload["external_context_injections"][0]["type"] == "human_resolution_ticket"
    assert isinstance(payload.get("hitl_alert"), dict)
    assert payload["hitl_alert"]["code"] == "NO_HITL_FEEDBACK_PRESENT"


def test_focus_resolver_system_message_mentions_binding_answered_unintegrated_guardrail() -> None:
    system_msg = build_focus_resolver_system_message()
    lower = system_msg.lower()
    assert "external_context_injections" in system_msg
    assert "blocker_feedback_state" in system_msg
    assert "answered_unintegrated" in lower
    assert "binding human_resolution_ticket" in lower
    assert "scripted checklist runner" in lower
    assert "emergent focus items" in lower
    assert "investigation_brief" in lower
    assert "do not ignore provided human feedback" in lower
    assert "startup understanding authors the initial focus" in lower
    assert "crop_box_normalized" in system_msg
    assert "zoom_factor" in system_msg
    # refine_region / grid_selection internal steps removed (D3-A clean vocab)
    assert "refine_region" not in system_msg
    assert "grid_selection" not in system_msg
    assert "propose_blocker_updates" in system_msg
    assert "propose_work_board_changes" in system_msg
    assert "work_board_changes" in system_msg
    assert "custom:<name>" in system_msg


def test_planner_system_message_mentions_investigation_brief_as_sticky_note() -> None:
    system_msg = build_planner_system_message()
    lower = system_msg.lower()
    assert "investigation brief" in lower
    assert "sticky note" in lower
    assert "item_context" in lower
    assert "continuity_context" in lower
    assert "evidence_context" in lower
    assert "do not behave like a scripted checklist runner" in lower
    assert "first bounded focus" in lower
    assert "execution_context.active_work_item" in system_msg
    assert "recent_iterations" in lower
    assert "working_plan" not in lower
    assert "policy_signals" not in lower
    assert "planner" in lower


def test_planner_user_message_carries_investigation_brief() -> None:
    payload = json.loads(
        build_planner_user_message(
            source_transcript_ref="in-memory://source.json",
            source_transcript_hash="sha256:test",
            findings_summary={},
            investigation_brief={"role": "sticky_note", "purpose": "current_case_understanding"},
            item_context={"role": "sticky_note", "purpose": "current_case_understanding"},
            continuity_context={"active_item_id": "range", "focus_source": "continuity"},
            evidence_context={"source_completeness": "unknown"},
            item_history=[{"decision_key": "range"}],
            unresolved_questions=["Resolve the range conflict."],
            top_findings=[],
            span_context=[],
            image_verification={},
            candidate_disagreement_hints={},
            mapping_priority_focus={},
        )
    )
    assert isinstance(payload.get("investigation_brief"), dict)
    assert str((payload.get("investigation_brief") or {}).get("role") or "") == "sticky_note"
    support_state = payload.get("support_state")
    assert isinstance(support_state, dict)
    assert str((support_state.get("item_context") or {}).get("role") or "") == "sticky_note"
    assert str((support_state.get("continuity_context") or {}).get("active_item_id") or "") == "range"
    assert str((support_state.get("evidence_context") or {}).get("source_completeness") or "") == "unknown"
    assert isinstance(support_state.get("item_history"), list)
    assert isinstance(support_state.get("unresolved_questions"), list)
    assert "policy_signals" not in payload


def test_planner_user_message_includes_slim_execution_context_with_recent_lane() -> None:
    ec = {
        "schema_version": "execution_context.v1",
        "parity": {"code": "ok", "identity_aligned": True, "posture_aligned": True},
        "focus_selection": {"decision_key": "range"},
        "active_work_item": {"item_id": "te:ledger:range", "state": "blocked"},
        "recent_iterations": {"schema_version": "recent_activity.v1", "rich_capsules": [{"iteration": 2}]},
        "blocker_posture": {
            "understanding_strength": "moderate",
            "needs_orientation": False,
            "needs_inventory": False,
            "has_fresh_signal": True,
            "cached_context_present": True,
            "repeat_without_signal": False,
        },
        "support_state": {
            "item_context": {
                "role": "sticky_note",
                "purpose": "current_case_understanding",
                "open_questions": ["x"],
                "recent_attempts": [{"move": "a"}, {"move": "b"}],
            },
            "continuity_context": {"active_item_id": "range", "focus_source": "continuity"},
            "evidence_context": {"source_completeness": "unknown", "recent_image_attempts": 1},
            "blocker_posture": {
                "understanding_strength": "moderate",
                "has_fresh_signal": True,
                "cached_context_present": True,
                "repeat_without_signal": False,
            },
        },
    }
    payload = json.loads(
        build_planner_user_message(
            source_transcript_ref="in-memory://source.json",
            source_transcript_hash="sha256:test",
            findings_summary={},
            investigation_brief=None,
            working_plan=None,
            policy_signals=None,
            top_findings=[],
            span_context=[],
            image_verification={},
            candidate_disagreement_hints={},
            mapping_priority_focus={},
            execution_context=ec,
        )
    )
    slim = payload.get("execution_context")
    assert isinstance(slim, dict)
    assert slim.get("active_work_item", {}).get("item_id") == "te:ledger:range"
    assert isinstance(slim.get("recent_iterations"), dict)
    assert slim.get("support_state", {}).get("item_context", {}).get("role") == "sticky_note"
    assert slim.get("support_state", {}).get("continuity_context", {}).get("active_item_id") == "range"
    assert "working_plan" not in (slim.get("support_state") or {})
    assert "policy_signals" not in (slim.get("support_state") or {})


def test_slim_planner_execution_context_bounded_working_plan() -> None:
    ec = {
        "support_state": {
            "item_context": {
                "recent_attempts": [{"move": "a"} for _ in range(5)],
                "open_questions": ["a", "b", "c", "d", "e"],
            },
            "continuity_context": {"active_item_id": "range"},
            "evidence_context": {"source_completeness": "unknown"},
        }
    }
    slim = slim_execution_context_for_planner(ec)
    assert slim is not None
    steps = (slim.get("support_state") or {}).get("item_context") or {}
    assert len(steps.get("open_questions") or []) <= 4


def test_focus_resolver_user_message_emits_hitl_alert_when_feedback_present() -> None:
    user_msg = build_focus_resolver_user_message(
        focus_packet={
            "decision_key": "range",
            "source_transcript_ref": "in-memory://source.json",
            "source_transcript_hash": "sha256:test",
            "item_context": {"role": "sticky_note", "purpose": "current_case_understanding"},
            "continuity_context": {"active_item_id": "range"},
            "evidence_context": {"source_completeness": "unknown"},
            "blocker_posture": {"understanding_strength": "weak", "has_fresh_signal": False, "cached_context_present": False},
            "feedback": {
                "decision_key": "range",
                "selected_value": "Range 75 West",
                "prompt_id": "hitl_range_1_x",
                "note": "Use range 75.",
            },
        }
    )
    payload = json.loads(user_msg)
    alert = payload.get("hitl_alert")
    assert isinstance(alert, dict)
    assert alert.get("code") == "HITL_FEEDBACK_PRESENT"
    assert str(alert.get("decision_key")) == "range"
    assert str(alert.get("selected_value")) == "Range 75 West"
    assert isinstance(payload.get("investigation_brief"), dict)
    assert isinstance(payload.get("item_context"), dict)
    assert isinstance(payload.get("continuity_context"), dict)
    assert isinstance(payload.get("evidence_context"), dict)
    handling = payload.get("required_feedback_handling")
    assert isinstance(handling, list)
    assert len(handling) >= 1
    assert isinstance(payload.get("blocker_feedback_state"), dict)
    assert isinstance(payload.get("blocker_resolution_protocol"), list)


def test_focus_resolver_repair_message_includes_injection_context_when_present() -> None:
    repair = build_focus_resolver_repair_user_message(
        error_reason="resolver_invalid:ValidationError:invalid_move",
        raw_content='{"move":"bad"}',
        decision_key="range",
        injection_context={
            "has_answered_unintegrated_ticket": True,
            "ticket_id": "hitl_range_1_x",
            "decision_key": "range",
            "lifecycle_state": "answered_unintegrated",
        },
        attempt=1,
        max_attempts=2,
    )
    payload = json.loads(repair)
    assert isinstance(payload.get("injection_context"), dict)
    assert payload["injection_context"]["has_answered_unintegrated_ticket"] is True
    assert "instruction" in payload


def test_focus_resolver_user_message_output_shape_prefers_normalized_select_region() -> None:
    payload = json.loads(
        build_focus_resolver_user_message(
            focus_packet={
                "decision_key": "range",
                "source_transcript_ref": "in-memory://source.json",
                "source_transcript_hash": "sha256:test",
            }
        )
    )
    output_shape = payload.get("output_shape") if isinstance(payload.get("output_shape"), dict) else {}
    evidence_request = output_shape.get("evidence_request") if isinstance(output_shape.get("evidence_request"), dict) else {}
    target = evidence_request.get("target") if isinstance(evidence_request.get("target"), dict) else {}
    # mode removed from example (A1 — no internal tool-step vocab in prompt)
    assert "mode" not in evidence_request
    assert isinstance(target.get("crop_box_normalized"), dict)
    assert "propose_blocker_updates" in list(payload.get("allowed_moves") or [])
    blocker_updates = output_shape.get("blocker_updates")
    assert isinstance(blocker_updates, list) and len(blocker_updates) >= 1


def test_system_message_crop_box_normalized_is_dict_shape() -> None:
    """A2: system message must describe crop_box_normalized as a dict, not a list."""
    msg = build_focus_resolver_system_message()
    assert '"x"' in msg or "\"x\"" in msg or '{"x"' in msg
    assert "[x0,y0,x1,y1]" not in msg


def test_output_shape_evidence_request_has_no_mode_field() -> None:
    """A1: output_shape evidence_request example must not contain a mode field."""
    payload = json.loads(
        build_focus_resolver_user_message(
            focus_packet={"decision_key": "range", "source_transcript_ref": "test", "source_transcript_hash": "abc"}
        )
    )
    er = (payload.get("output_shape") or {}).get("evidence_request") or {}
    assert "mode" not in er, "mode should not appear in evidence_request example (A1 clean vocab)"


def test_system_message_staged_hitl_image_evidence_guidance() -> None:
    """C: system message must include staged HITL pattern guidance."""
    msg = build_focus_resolver_system_message()
    assert "image_evidence step first" in msg or "one image_evidence step" in msg

