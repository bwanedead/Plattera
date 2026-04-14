"""Instruction text for action-plan repair mode."""

from __future__ import annotations

from .choose_action_instruction import ACTION_PLAN_SCHEMA_TEXT

REPAIR_INSTRUCTION: str = (
    "You are repairing a prior Plattera action-plan response after canonical parsing failed. "
    "The JSON packet below contains only the minimum repair context: available tool_ids, the prior response text and parse failure details, "
    "and optionally a pre-parsed previous_response_object and repair_targets listing the structural issues to fix.\n"
    + ACTION_PLAN_SCHEMA_TEXT
    + "Repair rules:\n"
    "- Preserve intended action semantics. Change only the fields needed to satisfy repair_targets.\n"
    "- If repair_context.previous_response_object is provided, treat it as the base object and make minimal targeted edits.\n"
    "- Do not rewrite sections unrelated to the identified structural problems.\n"
    "- When a required field is missing, add the smallest valid version rather than regenerating the whole plan.\n"
    "- continuity_journal_entry is optional (null is valid). If repair_targets includes add_missing_continuity_journal_entry, "
    "add a compact non-empty object such as {\"step\": \"recorded repair outcome\", \"open_threads\": [\"continue active investigation\"]}; "
    "do not invent semantic journal content beyond what is structurally required.\n"
    "- If repair_targets includes move_state_patch_closure_state_under_mission, relocate state_patch.closure_state into "
    "state_patch.mission.closure_state and remove the top-level key from state_patch.\n"
    "- Use action_type only from surface_packet.tool_ids, or null only for an explicit skip_execution state-authoring turn.\n"
    "- state_patch must be an object or null; mission and resolution belong only inside state_patch.\n"
    "- Do not invent host-only keys such as schema_version or updated_at_epoch_seconds.\n"
    "Return one JSON object only. No markdown. No commentary."
)
