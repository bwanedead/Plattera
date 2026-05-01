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


def test_choose_action_instruction_teaches_defensible_evidence_and_read_carry_forward() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "defensible evidence" in lowered
    assert "directly and undeniably auditable" in lowered
    assert "without reconstructing broad context" in lowered
    assert "focused crop, zoom, excerpt, trace, query result, test output, screenshot, log excerpt, code pointer" in lowered
    assert "falsely accused of incorrect work" in lowered
    assert "a read, hydrate, or transform is not complete" in lowered
    assert "persist that distinction immediately" in lowered
    assert "same_item_hydrate_churn_no_gain" in text


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


def test_surface_teaches_defensible_evidence_and_read_carry_forward() -> None:
    from harness.runtime.prompting.surface import _HARNESS_TRUNK_METHOD_TEXT
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "defensible evidence rule" in lowered
    assert "directly and undeniably auditable" in lowered
    assert "without reconstructing broad context" in lowered
    assert "falsely accused of incorrect work" in lowered
    assert "read carry-forward rule" in lowered
    assert "persist that distinction immediately" in lowered
    assert "same_item_hydrate_churn_no_gain" in text


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


def test_choose_action_instruction_teaches_source_and_downstream_lanes() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "source-observed lane" in lowered
    assert "downstream-usable lane" in lowered
    assert "do not silently overwrite the source lane" in lowered
    assert "mark the unavailable portion explicitly" in lowered


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


def test_choose_action_instruction_teaches_compact_atom_and_locator_doctrine() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    # Compact atom contract
    assert "compact atom contract" in lowered
    assert "compact claim atoms" in lowered
    assert "long_determined_value_units" in text
    # Considering rendering for candidate_values (allow smart quotes)
    assert "considering" in lowered
    assert "render" in lowered and "candidate_values" in text
    # Evidence refs vs evidence locators
    assert "evidence refs vs evidence locators" in lowered
    assert "agent authors" in lowered
    assert "earned_unit_missing_locator" in text
    # locator_kind mentions
    for kind in ("image_region", "text_span", "json_path"):
        assert kind in text
    # Label/title/unit_id ordering and human-facing label guidance
    assert "label" in lowered and "title" in lowered and "unit_id" in lowered
    assert "ui prefers" in lowered or "user-facing" in lowered
    assert "render locator artifacts" in lowered
    assert "the runtime only validates and renders it" in lowered
    assert "claim-local rendered evidence lets a reviewer" in lowered
    assert "broad evidence refs from hiding weak verification" in lowered


def test_choose_action_instruction_teaches_field_role_separation() -> None:
    text = CHOOSE_ACTION_INSTRUCTION
    lowered = text.lower()
    assert "field roles" in lowered
    assert "skeleton fields" in lowered
    assert "prose fields" in lowered
    assert "determined_value` is for compact resolved values only" in text
    assert "candidate_values` is for considered options, not exhaustive truth" in text
    assert "closure_summary` is the short memory retained after closure" in text
    assert "reopen_triggers` describe what would invalidate or reopen the row" in text
    assert "long text belongs in artifacts" in lowered
    assert "verification_basis` explains why a value is earned" in text


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
    assert "compact claim inventory lets future turns, audit, and ui surfaces" in lowered
    assert "without it, exact claims can enter final-looking output" in lowered


def test_choose_action_instruction_prompt_work_graph_projection_has_no_domain_examples() -> None:
    lowered = CHOOSE_ACTION_INSTRUCTION.lower()
    start = lowered.find("### prompt work-graph projection")
    end = lowered.find("### evidence refs vs evidence locators")
    assert start >= 0, "prompt work-graph projection section must exist"
    assert end > start, "evidence locator section should follow prompt projection section"
    section = lowered[start:end]
    for banned in ("deed", "parcel", "range", "bearing", "distance", "cutoff", "mapping"):
        assert banned not in section, f"Found banned term {banned!r} in prompt projection doctrine"


def test_choose_action_instruction_field_roles_have_no_domain_examples() -> None:
    lowered = CHOOSE_ACTION_INSTRUCTION.lower()
    start = lowered.find("field roles:")
    end = lowered.find("compact value fields on a covered unit")
    assert start >= 0, "field roles section must exist"
    assert end > start, "compact value section should follow field roles"
    section = lowered[start:end]
    for banned in ("deed", "parcel", "range", "bearing", "distance", "cutoff", "mapping"):
        assert banned not in section, f"Found banned term {banned!r} in field-role doctrine"


def test_choose_action_instruction_locator_rendering_has_no_domain_examples() -> None:
    lowered = CHOOSE_ACTION_INSTRUCTION.lower()
    start = lowered.find("### evidence refs vs evidence locators")
    end = lowered.find("if a focused locator is feasible")
    assert start >= 0 and end > start
    section = lowered[start:end]
    for banned in ("deed", "parcel", "range", "bearing", "distance", "cutoff", "mapping"):
        assert banned not in section, f"Found banned term {banned!r} in locator doctrine"


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


def test_state_repair_mode_excludes_bulky_step_records_fields() -> None:
    from harness.runtime.orchestration.prompt_modes import require_prompt_mode_spec
    spec = require_prompt_mode_spec("state_repair")
    assert "recent_kernel_step_records" not in spec.structured_state_fields
    assert "recent_kernel_step_result_records" not in spec.structured_state_fields
    # lean fields must still be present
    assert "recent_tool_result_slices" in spec.structured_state_fields
    assert "prompt_observability_summary" in spec.structured_state_fields
