"""Instruction text for resume-mode choose-action turns."""

from __future__ import annotations

from .choose_action_instruction import ACTION_PLAN_SCHEMA_TEXT

RESUME_INSTRUCTION: str = (
    "You are resuming an in-progress Plattera run after carried continuity or answered HITL context was restored. "
    "The JSON packet below keeps stable doctrine explicit while slimming the re-entry context to what you need to continue truthfully.\n"
    + ACTION_PLAN_SCHEMA_TEXT
    + "Resume rules: treat answered_hitl_responses as pending material only when they appear in run_context, "
    "and list any prompt ids you actually integrated in hitl_consumed_prompt_ids. "
    "Do not restart the mission from scratch when recent continuity already makes the next move clear. "
    "Keep using the same state_patch contract; do not copy host-only keys such as schema_version or updated_at_epoch_seconds into authored state. "
    "Return one JSON object only. No markdown. No commentary."
)
