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


def test_choose_action_instruction_teaches_operator_progress_message() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "operator_progress_message" in lowered
    assert "include it on every normal choose-action turn" in lowered
    assert "timeline/ui visibility" in lowered
    assert "keep detailed reasoning in `rationale`" in lowered
    assert "not internal reasoning" in lowered or "not internal reasoning" in text


def test_choose_action_instruction_teaches_native_turn_contract() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "### action execution" in lowered
    assert "one coherent plan" in lowered
    assert "what tools should run now (`actions`)" in lowered
    assert "what should be visible next turn (`hydrate_next`, `pin_refs`, `unpin_refs`)" in lowered
    assert "what durable state changed" in lowered
    assert "operator_progress_message` is the short user-facing intent line" in text
    assert "rationale` is the compact internal reason" in text


def test_choose_action_instruction_teaches_efficiency_reminders() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "### important reminders: efficient motion density" in lowered
    assert "each turn is expensive" in lowered
    assert "multiple `actions` rows are allowed" in lowered
    assert "do not batch theatrically" in lowered
    assert "avoid hydrate-only turns" in lowered
    assert "use `hydrate_next` when you already know the next turn must inspect a ref this action produces" in lowered
    assert "use `pin_refs` only for refs that will matter repeatedly across turns" in lowered
    assert "concrete expected gain" in lowered


def test_choose_action_instruction_teaches_pin_refs_as_attention_support() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "pin_refs" in text
    assert "unpin_refs" in text
    assert "small number of refs that should stay hot across turns" in lowered
    assert "mechanically carried forward and auto-surfaced/hydrated" in lowered
    assert "until it is unpinned or expires" in lowered
    assert "attention support, not proof" in lowered
    assert "prefer `hydrate_next` for one-shot next-turn visibility" in lowered
    assert "prefer `pin_refs` only when the same ref will likely matter across multiple turns" in lowered


def test_choose_action_instruction_teaches_delegate_subtask_sensibly() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "`delegate_subtask` is an observation tool" in text
    assert "parent supplies bounded task framing and context refs" in lowered
    assert "child returns observation only" in lowered
    assert "delegation does not update durable state" in lowered
    assert "delegation does not replace parent inventory" in lowered
    assert "batch multiple independent `delegate_subtask` rows" in lowered
    assert "target_entity_id" in text
    assert "opaque id so audit/ui can show what the delegate was for" in lowered
    assert "linkage metadata, not truth" in lowered


def test_choose_action_instruction_does_not_teach_legacy_action_batch() -> None:
    assert "action_batch" not in CHOOSE_ACTION_INSTRUCTION


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
    assert "stable_context" in text
    assert "durable orientation memory" in text
    assert "not evidence, truth, closure, work inventory, or instruction" in text
    assert "attached_entity_ids" in text
    assert "keep bodies bounded and high-signal" in text
    assert "work_universe_posture" in text
    assert "motion_posture" in text
    assert "motion_posture_basis" in text
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
    assert 'Minimal one-action dispatch:' in text
    assert 'Minimal existing-row update:' in text
    assert 'Minimal new row:' in text
    assert 'Minimal covered-unit group:' in text
    assert 'Minimal HITL:' in text
    assert 'Minimal complete:' in text
    assert '"actions":[{"alias":"load_ref","action_type":"hydrate_artifact_refs"' in text
    assert 'One action with next-turn hydration:' in text
    assert 'Multiple independent actions:' in text
    assert '@this.result.revision_ref' in text
    assert '@this.result.working_draft_ref' in text
    assert '@this.result.output_ref' in text
    assert '@this.result.derived_ref_id' in text
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


def test_choose_action_instruction_teaches_covered_unit_value_fields() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "compact atom contract" in lowered
    assert "label" in text and "value_kind" in text
    assert "candidate_values" in text
    assert "determined_value" in text
    assert "put it in `determined_value`" in text
    assert "not only in `summary` or `verification_basis`" in lowered
    assert "long_determined_value_units" in text


def test_choose_action_instruction_teaches_tool_result_carry_forward() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "### tool-result carry-forward" in lowered
    assert "floating tool results do not help unless integrated" in lowered
    assert "carry it into `state_patch`" in text
    assert "same_item_hydrate_churn_no_gain" in text


def test_choose_action_instruction_does_not_duplicate_surface_exact_proof_doctrine() -> None:
    lowered = CHOOSE_ACTION_INSTRUCTION.lower()
    assert "defensible evidence" not in lowered
    assert "localize first, then determine" not in lowered
    assert "evidence cannot be retroactive" not in lowered
    assert "false earned certainty" not in lowered
    assert "handoff readiness" not in lowered
    assert "itemization and per-item resolution" not in lowered


def test_surface_teaches_broad_to_specific_value_decomposition() -> None:
    from harness.runtime.prompting.surface import _HARNESS_TRUNK_METHOD_TEXT
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "mission work method" in lowered
    assert "work proximity, groups, and atoms" in lowered
    assert "candidate_values" in text
    assert "determined_value" in text
    assert "if the atomic row has an answer" in lowered
    assert "claim, candidates, determined value, evidence, status" in lowered
    assert "value_kind" in text
    assert "not exhaustive" in lowered
    assert "compact proof object" in lowered
    assert "work-universe quality directly affects the economic possibility cone" in lowered


def test_surface_teaches_defensible_evidence_and_read_carry_forward() -> None:
    from harness.runtime.prompting.surface import _HARNESS_TRUNK_METHOD_TEXT
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "defensible evidence" in lowered
    assert "directly and undeniably auditable" in lowered
    assert "without reconstructing broad context" in lowered
    assert "false determination — false earned certainty — is a common agent failure mode" in lowered
    assert "carries forward the wrong digit, mark, option, status, or value" in lowered
    assert "read carry-forward rule" in lowered
    assert "persist that distinction immediately" in lowered
    assert "same_item_hydrate_churn_no_gain" in text


def test_surface_teaches_group_covered_units_rule() -> None:
    from harness.runtime.prompting.surface import _HARNESS_TRUNK_METHOD_TEXT
    text = _HARNESS_TRUNK_METHOD_TEXT.lower()
    assert "covered_units" in text
    assert "atoms are the core completeness unit" in text
    assert "groups are organizational utilities" in text
    assert "the material atoms inside the mission have visible places" in text
    assert "success, failure, handoffability, safety, cost, user trust" in text
    assert "ask the smallest question whose answer can be integrated" in text


def test_resume_instruction_mentions_remaining_hitls_and_audit_requirement() -> None:
    text = RESUME_INSTRUCTION.lower()
    assert "other pending hitls remain live" in text
    assert "additional async hitls" in text
    assert "work_universe_posture `audited`" in text
    assert "integrate the answer into durable state explicitly" in text


def test_choose_action_instruction_teaches_hitl_repair_not_reask() -> None:
    text = CHOOSE_ACTION_INSTRUCTION.lower()
    assert "repair the integration patch" in text
    assert "re-asking when a valid answer already exists" in text


def test_choose_action_instruction_teaches_artifact_excerpt_boundary_risk_flag() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "artifact_excerpt_boundary_risk" in text
    assert "outputs_structural_metadata" in text
    assert "do not infer" in lowered or "not infer" in lowered
    assert "absent from the excerpt" in lowered or "absent from the source" in lowered


def test_choose_action_instruction_teaches_generic_multi_lane_preflight() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "multiple semantic lanes or views" in lowered
    assert "preserve each required lane when they differ" in lowered
    assert "do not silently collapse one lane into another" in lowered
    assert "carry metadata explaining divergence" in lowered
    assert "source-observed lane" not in lowered
    assert "downstream-usable lane" not in lowered


def test_choose_action_instruction_preflight_section_has_no_current_deed_examples() -> None:
    lowered = CHOOSE_ACTION_INSTRUCTION.lower()
    preflight_idx = lowered.find("### save/complete shape preflight")
    assert preflight_idx >= 0, "save/complete shape preflight section must exist"
    section = lowered[preflight_idx:]
    for banned in ("range 75", "range 74", "parcel 1", "parcel 2", "bearing", "1638"):
        assert banned not in section, f"Found banned term {banned!r} in choose-action lane/preflight sections"


def test_choose_action_instruction_teaches_artifact_shape_preflight_without_hitl() -> None:
    text = CHOOSE_ACTION_INSTRUCTION.lower()
    assert "save/complete shape preflight" in text
    assert "latest_artifact_ref" in text
    assert "field presence/length signals" in text
    assert "outputs_excerpt" in text
    assert "use the excerpt first when it is complete" in text
    assert "repair and save again" in text
    assert "not to ask hitl" in text or "not to ask hitl whether the artifact is complete" in text


def test_choose_action_instruction_teaches_hitl_consumed_prompt_ids_placement() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "hitl_consumed_prompt_ids" in text
    assert "top-level action plan" in lowered or "top level of the action plan" in lowered
    assert "not inside `state_patch`" in text or "not a `state_patch` or `state_patch.mission` field" in text


def test_choose_action_instruction_teaches_terminal_summary_is_host_owned() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    # terminal_summary must be called out as host-owned, not a model field
    assert "terminal_summary" in text
    assert "host-owned" in text.lower()


def test_repair_instruction_teaches_hitl_consumed_placement() -> None:
    from harness.runtime.orchestration.repair_instruction import REPAIR_INSTRUCTION, STATE_REPAIR_INSTRUCTION
    for name, text in (("REPAIR_INSTRUCTION", REPAIR_INSTRUCTION), ("STATE_REPAIR_INSTRUCTION", STATE_REPAIR_INSTRUCTION)):
        assert "hitl_consumed_prompt_ids" in text, f"{name} missing hitl_consumed_prompt_ids guidance"
        assert "top-level action plan field" in text, f"{name} missing top-level placement guidance"


def test_repair_instruction_teaches_terminal_summary_removal() -> None:
    from harness.runtime.orchestration.repair_instruction import REPAIR_INSTRUCTION, STATE_REPAIR_INSTRUCTION
    for name, text in (("REPAIR_INSTRUCTION", REPAIR_INSTRUCTION), ("STATE_REPAIR_INSTRUCTION", STATE_REPAIR_INSTRUCTION)):
        assert "terminal_summary" in text, f"{name} missing terminal_summary guidance"
        assert "host-owned" in text.lower(), f"{name} missing host-owned reference"


def test_choose_action_instruction_teaches_compact_atom_and_locator_mechanics() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "compact atom contract" in lowered
    assert "long_determined_value_units" in text
    assert "evidence refs vs evidence locators" in lowered
    assert "you author locators" in lowered
    assert "earned_unit_missing_locator" in text
    for kind in ("image_region", "text_span", "json_path"):
        assert kind in text
    assert "closure_summary" in text and "reopen_triggers" in text


def test_choose_action_instruction_teaches_notebook_shape_flag_guidance() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "notebook_shaped_graph_rows" in text
    assert "advisory only" in lowered
    assert "move long content to prose/artifact fields" in lowered
    assert "keep exact claims in compact fields" in lowered


def test_choose_action_instruction_teaches_artifact_claim_inventory_suspect_guidance() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "artifact_claim_inventory_suspect" in text
    assert "advisory only, not a completion gate" in lowered
    assert "do not treat the artifact alone as proof of completion" in lowered
    assert "create or update atomic items or covered units" in lowered
    assert "if the mission truly does not require atomization" in lowered
    assert "label it honestly" in lowered
    assert "do not reread just to reduce discomfort" in lowered


def test_choose_action_instruction_prompt_work_graph_projection_has_no_domain_examples() -> None:
    lowered = CHOOSE_ACTION_INSTRUCTION.lower()
    start = lowered.find("### prompt work-graph projection")
    end = lowered.find("### evidence refs vs evidence locators")
    assert start >= 0, "prompt work-graph projection section must exist"
    assert end > start, "evidence locator section should follow prompt projection section"
    section = lowered[start:end]
    for banned in ("deed", "parcel", "range", "bearing", "distance", "cutoff", "mapping"):
        assert banned not in section, f"Found banned term {banned!r} in prompt projection doctrine"


def test_choose_action_instruction_locator_mechanics_have_no_domain_examples() -> None:
    lowered = CHOOSE_ACTION_INSTRUCTION.lower()
    start = lowered.find("### evidence refs vs evidence locators")
    end = lowered.find("- if order matters, use `sequence_scope`")
    assert start >= 0 and end > start
    section = lowered[start:end]
    for banned in ("deed", "parcel", "range", "bearing", "distance", "cutoff", "mapping"):
        assert banned not in section, f"Found banned term {banned!r} in locator mechanics"


def test_surface_teaches_compact_claim_atoms_and_locator_doctrine() -> None:
    from harness.runtime.prompting.surface import _HARNESS_TRUNK_METHOD_TEXT
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "compact claim atoms" in lowered
    assert "considering" in lowered
    assert "evidence refs vs evidence locators" in lowered
    assert "deterministic code does not invent" in lowered or "agent authors locators" in lowered
    assert "claim-local rendered evidence lets a reviewer" in lowered
    assert "image regions" in lowered
    assert "json paths" in lowered


def test_choose_action_instruction_teaches_truncation_boundary_doctrine() -> None:
    """text_field_summaries and prompt-projection-boundary doctrine must be present and domain-free."""
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    # Core vocabulary
    assert "text_field_summaries" in text
    assert "is_complete" in text
    assert "outputs_excerpt_truncated" in text
    # Must explain that excerpt_truncated is a projection boundary, not artifact boundary
    assert "prompt projection" in lowered or "projection boundary" in lowered
    # Must mention focused/targeted read as the alternative
    assert "focused" in lowered
    # Must discourage broad re-hydration for truncation recovery
    assert "re-hydrat" in lowered or "broad re-hydration" in lowered
    # No domain-specific terms in the surrounding doctrine block
    start = lowered.find("outputs_excerpt_truncated")
    assert start >= 0
    section = lowered[start: start + 800]
    for banned in ("deed", "parcel", "transcript_edit", "bearing", "distance", "acreage"):
        assert banned not in section, f"Found domain term {banned!r} in truncation-boundary doctrine"


def test_state_repair_mode_excludes_bulky_step_records_fields() -> None:
    from harness.runtime.orchestration.prompt_modes import require_prompt_mode_spec
    spec = require_prompt_mode_spec("state_repair")
    assert "recent_kernel_step_records" not in spec.structured_state_fields
    assert "recent_kernel_step_result_records" not in spec.structured_state_fields
    # lean fields must still be present
    assert "recent_tool_result_slices" in spec.structured_state_fields
    assert "prompt_observability_summary" in spec.structured_state_fields
