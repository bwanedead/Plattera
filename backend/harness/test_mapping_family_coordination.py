from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.mission_runtime.contracts import TerminalRecommendation
from harness.mission_runtime.mapping_family import build_mapping_family_coordination


def test_mapping_family_ready_posture_recommends_expected_next_mode() -> None:
    coordination = build_mapping_family_coordination(
        current_mode="transcript_edit",
        handoff_posture={
            "posture": "ready_for_downstream_domain",
            "target_domain_id": "deed_to_ir",
            "target_family_id": "mapping",
            "reason_code": "tx_agent_clean_complete",
            "summary": "Transcript-edit can hand off validated artifacts downstream.",
        },
        terminal=TerminalRecommendation(terminal=True, terminal_class="completed", reason_code="tx_agent_clean_complete"),
        transition_allowed=True,
        handed_forward_artifact_refs=["artifact://tx/run/1"],
        resume_note_for_prior_mode="return to transcript_edit only if new closure blockers emerge",
    )

    assert coordination.family_id == "mapping"
    assert coordination.current_mode == "transcript_edit"
    assert coordination.posture == "ready_for_downstream_domain"
    assert coordination.coordination_state == "transition_recommended"
    assert coordination.transition_recommendation is not None
    assert coordination.transition_recommendation.next_mode == "deed_to_ir"
    assert not hasattr(coordination.transition_recommendation, "expected_next_work")


def test_mapping_family_blocked_and_waiting_postures_do_not_recommend_transitions() -> None:
    blocked = build_mapping_family_coordination(
        current_mode="deed_to_ir",
        handoff_posture={
            "posture": "blocked_pending_dependency",
            "target_domain_id": "transcript_edit",
            "target_family_id": "mapping",
            "reason_code": "deed_to_ir_missing_required_dependency",
            "summary": "Deed output remains blocked by unresolved structural requirements before transcript-edit review.",
        },
        terminal=TerminalRecommendation(terminal=True, terminal_class="failed", reason_code="blocked"),
        transition_allowed=True,
    )
    waiting = build_mapping_family_coordination(
        current_mode="transcript_edit",
        handoff_posture={
            "posture": "waiting_on_human",
            "target_family_id": "mapping",
            "reason_code": "tx_agent_waiting_feedback",
            "summary": "Transcript-edit is waiting on human feedback.",
        },
        terminal=TerminalRecommendation(terminal=True, terminal_class="waiting_human", reason_code="tx_agent_waiting_feedback"),
        transition_allowed=True,
    )

    assert blocked.coordination_state == "blocked_pending_dependency"
    assert blocked.transition_recommendation is None
    assert waiting.coordination_state == "waiting_on_human"
    assert waiting.transition_recommendation is None
