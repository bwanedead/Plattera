from __future__ import annotations

from harness.runtime.orchestration.choose_action_instruction import CHOOSE_ACTION_INSTRUCTION
from harness.runtime.orchestration.resume_instruction import RESUME_INSTRUCTION


def test_choose_action_instruction_teaches_minimality_and_sparse_updates() -> None:
    text = CHOOSE_ACTION_INSTRUCTION.lower()
    assert "emit the smallest valid object" in text
    assert "omit irrelevant keys" in text
    assert "existing rows" in text
    assert "identity + changed fields only" in text
    assert "omitted stable fields remain unchanged" in text
    assert "do not author transport-only ceremony such as `idempotency_key`" in text
    assert 'async hitl: `{"hitl_request": {...}, "rationale": "..."}`' in text


def test_choose_action_instruction_requires_rationale_on_every_turn() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    assert "REQUIRED on every turn" in text
    assert "why this move now" in text
    assert "what new distinction or gain is expected" in text
    lowered = text.lower()
    assert "rationale is required" in lowered
    assert "missing or blank rationale" in lowered


def test_choose_action_instruction_teaches_state_patch_and_hitl_reference_law() -> None:
    text = CHOOSE_ACTION_INSTRUCTION.lower()
    assert "work_universe_posture" in text
    assert "complete_run" in text and "mechanical complete/publish gate" in text
    assert "mission_state" in text and "resolution_state" in text
    assert "hitl_request.context" in text
    assert "independently-resolvable unit" in text
    assert "structure_kind" in text
    assert "sequence_scope" in text
    assert "sequence_index" in text
    assert "subclaim_of" in text
    assert "prerequisite_of" in text
    assert "dependency graph" in text
    assert "primary_evidence_ref" in text
    assert "question_regions" in text
    assert "strongest available verification method" in text
    assert "unable to determine" in text
    assert "other / needs nuance" in text
    assert "what would have to be true in reality" not in text
    assert "peer agreement is a clue" not in text


def test_choose_action_instruction_omits_idempotency_from_model_facing_shapes() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    assert '"idempotency_key"' not in text


def test_choose_action_instruction_includes_tiny_examples() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    assert 'Minimal dispatch:' in text
    assert 'Minimal existing-row update:' in text
    assert 'Minimal new row:' in text
    assert 'Minimal HITL:' in text
    assert 'Minimal complete:' in text
    assert '{"action_type":"hydrate_artifact_refs"' in text
    assert '{"complete_run":true' in text


def test_resume_instruction_mentions_remaining_hitls_and_audit_requirement() -> None:
    text = RESUME_INSTRUCTION.lower()
    assert "other pending hitls remain live" in text
    assert "additional async hitls" in text
    assert "work_universe_posture `audited`" in text
    assert "integrate the answer into durable state explicitly" in text
