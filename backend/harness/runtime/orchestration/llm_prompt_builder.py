"""Choose-action prompt construction for kernel LLM turns.

Assembles the JSON envelope passed to the model on each kernel turn.
Instruction text lives in ``choose_action_instruction``.
Prompt-visible sanitization helpers live in ``prompt_sanitization``.
Shared serialization utility ``jsonable`` is re-exported for adapter-side use.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..hitl.transport import hitl_prompt_visible_slice
from ..memory.continuity_journal import (
    recent_journal_entries_for_prompt,
    recent_step_records_for_prompt,
    recent_step_result_records_for_prompt,
)
from ..composition import ComposedTurnInput
from .choose_action_instruction import CHOOSE_ACTION_INSTRUCTION
from .contracts import OrchestratorContext, SharedStateProjection
from .loop_health_summary import build_prompt_observability_summary
from .prompt_sanitization import projection_document, turn_input_document
from .prompt_utils import jsonable  # re-exported: callers import jsonable from here

_HIDDEN_LAUNCH_CONTEXT_KEYS = frozenset({"max_iterations"})
_PROMPT_VISIBLE_DOMAIN_CLOSURE_POLICY_KEYS = frozenset(
    {
        "hard_enforced",
        "enforce_on_publish",
        "enforce_on_complete",
        "minimum_resolution_items_for_save",
        "minimum_resolution_items_for_wait",
        "minimum_resolution_items_for_publish",
        "minimum_resolution_items_for_complete",
        "required_dimension_ids",
    }
)


def build_choose_action_prompt(
    *,
    composed_input: ComposedTurnInput,
    opaque_launch_context: Mapping[str, Any],
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
    journal_verbatim_keep_n: int,
) -> str:
    """Assemble the full choose-action prompt string for one kernel turn."""
    cont = context.loop_memory.continuity
    hitl_pend, hitl_ans, hitl_st = hitl_prompt_visible_slice(context.loop_memory.hitl)
    envelope = {
        "iteration": context.loop_memory.iterations,
        "session_id": context.session_id,
        "request_id_prefix": context.request_id_prefix,
        "launch_context": prompt_visible_launch_context(opaque_launch_context),
        "turn_input": turn_input_document(composed_input),
        "latest_refs": dict(cont.latest_refs),
        "active_item_id": cont.active_item_id,
        "state_patch_feedback": dict(cont.state_patch_feedback),
        "contract_feedback": jsonable(context.loop_memory.contract_feedback),
        "operator_progress_message": cont.operator_progress_message,
        "compacted_continuity_summary": cont.compacted_continuity_summary,
        "recent_continuity_journal_entries": recent_journal_entries_for_prompt(
            cont.continuity_journal_entries,
            cont.kernel_step_records,
            cont.kernel_step_result_records,
            keep_n=journal_verbatim_keep_n,
        ),
        "recent_kernel_step_records": recent_step_records_for_prompt(
            cont.continuity_journal_entries,
            cont.kernel_step_records,
            cont.kernel_step_result_records,
            keep_n=journal_verbatim_keep_n,
        ),
        "recent_kernel_step_result_records": recent_step_result_records_for_prompt(
            cont.continuity_journal_entries,
            cont.kernel_step_records,
            cont.kernel_step_result_records,
            keep_n=journal_verbatim_keep_n,
        ),
        "prompt_observability_summary": build_prompt_observability_summary(context.loop_memory),
        "hitl_state": hitl_st,
        "pending_hitl_requests": hitl_pend,
        "answered_hitl_responses": hitl_ans,
        "projection": projection_document(projection),
    }
    return CHOOSE_ACTION_INSTRUCTION + "\n\n" + json.dumps(envelope, ensure_ascii=False, sort_keys=True)


def prompt_visible_launch_context(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the launch-context slice that should be visible to the model.

    Host budget mechanics such as ``max_iterations`` are intentionally withheld so
    the model optimizes for truthful progress, not turn-count compression.
    """
    visible: dict[str, Any] = {}
    for key, raw_value in value.items():
        skey = str(key)
        if skey in _HIDDEN_LAUNCH_CONTEXT_KEYS:
            continue
        if skey == "domain_closure_policy" and isinstance(raw_value, Mapping):
            visible[skey] = {
                str(inner_key): jsonable(inner_value)
                for inner_key, inner_value in raw_value.items()
                if str(inner_key) in _PROMPT_VISIBLE_DOMAIN_CLOSURE_POLICY_KEYS
            }
            continue
        visible[skey] = jsonable(raw_value)
    return visible
