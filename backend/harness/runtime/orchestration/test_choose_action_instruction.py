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
    assert "smallest question whose answer can be integrated into a specific item or covered unit" in text
    assert "direct outcomes" in text
    assert "operator guessing" in text
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
    assert 'Minimal covered-unit group:' in text
    assert 'Minimal HITL:' in text
    assert 'Minimal complete:' in text
    assert '{"action_type":"hydrate_artifact_refs"' in text
    assert '{"complete_run":true' in text
    assert "Use option A" in text
    assert "Which source value should govern this item?" in text
    assert "Range" not in text
    assert "parcel" not in text.lower()


def test_choose_action_instruction_teaches_covered_units_merge_and_group_rule() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "covered_units" in text
    assert "merges covered_units by `unit_id`" in text
    # New units must carry unit_id and title.
    assert "new units must carry `unit_id` and `title`" in text
    # Two allowed shapes for a group's sub-units — either separate atomic items with relations,
    # or one group item carrying covered_units.
    assert "group item" in lowered
    assert "separate atomic `resolution.items`" in text
    assert "subclaim_of" in text
    assert "`covered_units` list" in text
    assert "do not mix both for the same sub-unit set" in lowered
    assert "do not hide critical sub-units only inside summary prose" in lowered
    assert "material sub-units are explicit as `covered_units` or separate related items" in text
    assert "covered-unit fields" in lowered


def test_choose_action_instruction_teaches_covered_unit_value_fields() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "label" in text and "value_kind" in text
    assert "candidate_values" in text
    assert "determined_value" in text
    assert "not exhaustive" in lowered
    assert "if another possibility appears, add it" in lowered
    assert "authoritative evidence earns disputed values" in lowered
    assert "bucket" in lowered and "group" in lowered and "atomic covered unit" in lowered
    assert "if this fails i will patch/block/escalate" in lowered or "stop condition" in lowered


def test_surface_teaches_broad_to_specific_value_decomposition() -> None:
    from harness.runtime.prompting.surface import _HARNESS_TRUNK_METHOD_TEXT
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "broad-to-specific value decomposition" in lowered
    assert "candidate_values" in text
    assert "determined_value" in text
    assert "value_kind" in text
    assert "not exhaustive" in lowered
    assert "authoritative evidence earns disputed values" in lowered
    assert "patch/block/escalate" in lowered or "stop condition" in lowered


def test_surface_teaches_group_covered_units_rule() -> None:
    from harness.runtime.prompting.surface import _HARNESS_TRUNK_METHOD_TEXT
    text = _HARNESS_TRUNK_METHOD_TEXT.lower()
    assert "covered_units" in text
    assert "may not close while a material sub-unit it stands over is still unresolved" in text
    assert "visible problem universe" in text
    assert "mission outcome, confidence, handoffability, safety, cost, or user trust" in text
    assert "ask the smallest question whose answer can be integrated" in text


def test_resume_instruction_mentions_remaining_hitls_and_audit_requirement() -> None:
    text = RESUME_INSTRUCTION.lower()
    assert "other pending hitls remain live" in text
    assert "additional async hitls" in text
    assert "work_universe_posture `audited`" in text
    assert "integrate the answer into durable state explicitly" in text
