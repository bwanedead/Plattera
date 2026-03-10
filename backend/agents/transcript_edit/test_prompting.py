from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.prompting import (
    build_focus_resolver_system_message,
    build_focus_resolver_repair_user_message,
    build_focus_resolver_user_message,
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
    assert "do not ignore provided human feedback" in lower
    assert "crop_box_normalized" in system_msg
    assert "refine_region" in system_msg
    assert "grid_selection only as fallback" in lower


def test_focus_resolver_user_message_emits_hitl_alert_when_feedback_present() -> None:
    user_msg = build_focus_resolver_user_message(
        focus_packet={
            "decision_key": "range",
            "source_transcript_ref": "in-memory://source.json",
            "source_transcript_hash": "sha256:test",
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
    assert str(evidence_request.get("mode") or "") == "select_region"
    assert isinstance(target.get("crop_box_normalized"), dict)
