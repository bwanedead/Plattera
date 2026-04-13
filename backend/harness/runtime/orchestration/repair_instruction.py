"""Instruction text for action-plan repair mode."""

from __future__ import annotations

from .choose_action_instruction import ACTION_PLAN_SCHEMA_TEXT

REPAIR_INSTRUCTION: str = (
    "You are repairing a prior Plattera action-plan response after canonical parsing failed. "
    "The JSON packet below contains only the minimum repair context: available tool_ids plus the prior response text and parse failure details. "
    "Preserve the intended action semantics if they are recoverable; change only what is needed to return one valid action-plan object.\n"
    + ACTION_PLAN_SCHEMA_TEXT
    + "Repair rules: continuity_journal_entry must be a non-empty object. "
    "Use action_type only from surface_packet.tool_ids, or null only for an explicit skip_execution state-authoring turn. "
    "state_patch must be an object or null; mission and resolution belong only inside state_patch. "
    "Do not invent host-only keys such as schema_version or updated_at_epoch_seconds. "
    "Return one JSON object only. No markdown. No commentary."
)
