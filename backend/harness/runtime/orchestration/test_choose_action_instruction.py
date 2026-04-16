from __future__ import annotations

from harness.runtime.orchestration.choose_action_instruction import CHOOSE_ACTION_INSTRUCTION
from harness.runtime.orchestration.resume_instruction import RESUME_INSTRUCTION


def test_choose_action_instruction_teaches_work_universe_posture_and_hitl_context() -> None:
    text = CHOOSE_ACTION_INSTRUCTION.lower()
    assert "work_universe_posture" in text
    assert "complete_run" in text and "mechanically blocked" in text
    assert "mission_state" in text and "resolution_state" in text
    assert "primary_evidence_ref" in text
    assert "annotated_evidence_ref" in text
    assert "question_regions" in text
    assert "unable to determine" in text
    assert "other / needs nuance" in text


def test_resume_instruction_mentions_remaining_hitls_and_audit_requirement() -> None:
    text = RESUME_INSTRUCTION.lower()
    assert "other pending hitls remain live" in text
    assert "additional async hitls" in text
    assert "work_universe_posture `audited`" in text
    assert "integrate the answer into durable state explicitly" in text
