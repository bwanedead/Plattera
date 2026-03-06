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


def test_focus_resolver_system_message_mentions_binding_answered_unintegrated_guardrail() -> None:
    system_msg = build_focus_resolver_system_message()
    lower = system_msg.lower()
    assert "external_context_injections" in system_msg
    assert "answered_unintegrated" in lower
    assert "binding human_resolution_ticket" in lower


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
