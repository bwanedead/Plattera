"""Instruction text for action-plan repair mode."""

from __future__ import annotations

from .choose_action_instruction import ACTION_PLAN_SCHEMA_TEXT

REPAIR_INSTRUCTION: str = (
    "You are repairing a prior Plattera action-plan response after canonical parsing failed. "
    "The JSON packet below contains only the minimum repair context: available tool_ids, the prior response text and parse failure details, "
    "and optionally a pre-parsed previous_response_object and repair_targets listing the structural issues to fix.\n"
    + ACTION_PLAN_SCHEMA_TEXT
    + """Repair rules:
- Preserve intended action semantics. Change only the fields needed to satisfy repair_targets.
- When repair_context.previous_response_object contains a native `actions` array, keep using native `actions` in the repaired output. Do not collapse a multi-action plan into a single `action_type` / `action_inputs` legacy shape unless the parse error explicitly requires removing extra rows.
- When repair_targets includes preserve_multi_action_intent or preserve_native_actions_array, retain as many valid action rows as the tool batch caps allow. If the prior plan exceeded a per-tool cap, trim to the cap by dropping the lowest-priority rows — never collapse to one action unless only one row was valid.
- When repair_targets includes reduce_actions_to_tool_cap_not_single_action, return the maximum allowed number of action rows (up to the cited cap), not one row.
- When repair_targets includes remove_top_level_hydrate_when_using_per_action_hydrate, remove top-level `hydrate_next` / `hydrate_next_reason` and keep per-row `hydrate_next` on each `actions[]` entry.
- When repair_targets includes repair_or_drop_malformed_action_rows_preserve_valid_rows, fix or drop only the malformed `actions[]` rows cited in the parse error; keep other valid rows unchanged.
- Per-action `hydrate_next` may use `@this.result.derived_ref_id`, `@this.result.revision_ref`, `@this.result.working_draft_ref`, `@this.result.published_ref`, `@this.result.output_ref`, or `@this.result.artifact_refs[]` on each row. Do not rewrite them to top-level `hydrate_next` or legacy `@result.*` unless repairing a single-action legacy plan.
- If repair_context.previous_response_object is provided, treat it as the base object and make minimal targeted edits.
- Do not rewrite sections unrelated to the identified structural problems.
- When a required field is missing, add the smallest valid version rather than regenerating the whole plan.
- rationale is required on every turn. If repair_targets includes add_missing_rationale, add the shortest honest rationale consistent with the action already chosen in the previous_response_object. Do not invent new decisions. Do not pad with doctrine or a generic filler sentence. Name why this move and what gain is expected — for example, if the original move was a hydrate of a specific ref, the rationale should state what that hydrate was meant to verify and what will happen if it yields nothing new.
- continuity_journal_entry is optional (null is valid) because the host records a canonical per-turn continuity record from rationale and outcome. If repair_targets includes add_missing_continuity_journal_entry, add a compact non-empty object such as {"step": "recorded repair outcome", "open_threads": ["continue active investigation"]}; do not invent semantic journal content beyond what is structurally required.
- continuity_journal_entry must be the raw author payload only. Do not wrap it inside host-shaped keys such as `author_payload` or `kernel_turn_index`; if those wrappers are present in the broken response, unwrap them during repair.
- If repair_targets includes move_state_patch_closure_state_under_mission, relocate state_patch.closure_state into state_patch.mission.closure_state and remove the top-level key from state_patch.
- Use canonical `state_patch.mission` and `state_patch.resolution` only. If the broken response used alias keys such as `mission_state` or `resolution_state`, rewrite them to the canonical keys during repair.
- Use `action_type` only from `surface_packet.tool_ids`, or omit/null `action_type` only for a no-dispatch state/HITL turn.
- state_patch must be an object or null; mission and resolution belong only inside state_patch.
- Do not invent host-only keys such as schema_version or updated_at_epoch_seconds.
- `hitl_consumed_prompt_ids` is a top-level action plan field, not a `state_patch.mission` field. If the broken response placed it inside mission or elsewhere in state_patch, move it to the top level of the action plan object during repair.
- `terminal_summary` is host-owned. It must not appear inside `state_patch.mission` or anywhere in the action plan. If the broken response included it, remove it.
- HITL answer integration belongs in item fields such as `notes`, `verification_basis`, `determined_value`, or `evidence_refs` — not in fabricated host-shaped wrapper keys.
Return one JSON object only. No markdown. No commentary."""
)

STATE_REPAIR_INSTRUCTION: str = (
    "You are repairing the durable proof state after the prior Plattera turn hit a mechanical state_patch problem or dropped state rows. "
    "The JSON packet below keeps the normal choose-action context, but the focus of this turn is the repair target surfaced in state_patch_feedback.\n"
    + ACTION_PLAN_SCHEMA_TEXT
    + """State-repair rules:
- Preserve already-earned mission understanding unless current evidence actually changes it.
- Treat state_patch_feedback as the repair target. Use its reason_code, failing_path, validation_errors, repair_targets, repair_hint, row_skips, and row_skip_details when present.
- Prefer the smallest acceptable delta: patch only the failing mission.success_conditions row, closure_state dimension row, or resolution item rows instead of rewriting large blocks.
- Keep already-earned findings, evidence refs, and closed items intact unless the repair target itself requires correction.
- If semantic intent is still fine and only state shape was malformed, prefer a minimal no-dispatch state-authoring turn.
- If the failure is a shape seam such as `mission_state` / `resolution_state` alias keys or a wrapped continuity journal payload, repair only that seam and preserve the semantic content intact.
- continuity_journal_entry must remain the raw author payload only; do not emit nested `author_payload` or `kernel_turn_index` wrappers.
- If the feedback reveals that proof is actually missing rather than malformed, you may choose a stronger bounded check instead of another state-only repair.
- Do not invent host-only keys such as schema_version or updated_at_epoch_seconds.
- `hitl_consumed_prompt_ids` is a top-level action plan field, not a `state_patch.mission` field. If the broken response placed it inside mission or elsewhere in state_patch, move it to the top level of the action plan object during repair.
- `terminal_summary` is host-owned. It must not appear inside `state_patch.mission` or anywhere in the action plan. If the broken response included it, remove it.
- HITL answer integration belongs in item fields such as `notes`, `verification_basis`, `determined_value`, or `evidence_refs` — not in fabricated host-shaped wrapper keys.
Return one JSON object only. No markdown. No commentary."""
)
