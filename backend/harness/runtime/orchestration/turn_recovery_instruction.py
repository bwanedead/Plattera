"""Instruction text for slim recovery after recoverable model-output failure."""

from __future__ import annotations

from .choose_action_instruction import ACTION_PLAN_SCHEMA_TEXT

TURN_RECOVERY_INSTRUCTION: str = (
    "You are recovering from a prior model turn that produced no usable action plan "
    "because the provider output was truncated, empty, or the action plan remained "
    "contract-invalid after repair. "
    "The run state was not mutated by that failed turn.\n"
    + ACTION_PLAN_SCHEMA_TEXT
    + "Recovery rules: return one small valid JSON object only. "
    "Do not restate doctrine, source text, large artifacts, or broad graph summaries. "
    "Use run_context.turn_recovery to see the bounded failed-turn metadata. "
    "Use surface_packet.tool_contracts for compact per-tool request shapes and batching "
    "when present; do not invent request fields, and honor projected batching limits "
    "(for example, do not emit multiple rows for a tool with batching.allowed=false). "
    "Inspect that metadata and emit the smallest valid action-plan JSON. "
    "Do not reconstruct or copy the failed action object: that object is the failure, not a draft to finish, "
    "and replaying it re-enters the same truncation or contract-invalid dead-end. "
    "If answered_hitl_responses are present, integrate the relevant answer with the smallest "
    "state_patch you can author and list consumed ids in hitl_consumed_prompt_ids. "
    "Preserve the human answer exactly; do not choose a different candidate because stale "
    "candidate values remain visible. "
    "If the next move is not HITL integration, take one bounded action that advances the active item. "
    "No markdown. No commentary."
)
