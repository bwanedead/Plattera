from __future__ import annotations

from typing import Any

from harness.orchestration_kernel.contracts import MoveDecision, MoveExecutionPlan, OrchestratorContext

from .execution_action_ids import TX_APPLY_EDIT_PLAN
from .execution_support import compile_transcript_edit_execution_support
from .loop_runtime import idempotency_key as _make_idempotency_key


def compile_transcript_edit_move(
    pack: Any,
    context: OrchestratorContext,
    move_decision: MoveDecision,
) -> MoveExecutionPlan:
    request = pack._request
    payload = move_decision.domain_move_payload
    focus_key = move_decision.focus_key or ""
    iterations = context.loop_memory.iterations
    idempotency_prefix = f"{pack._request_id_prefix}:{focus_key}:{iterations}"

    if move_decision.move_type == "apply_edit_plan":
        edit_plan = payload.get("edit_plan") if isinstance(payload.get("edit_plan"), dict) else {}
        inputs: dict[str, Any] = {
            "dossier_id": request.dossier_id,
            "edit_plan": edit_plan,
            "decision_key": focus_key,
        }
        if pack._state.current_transcript_ref:
            inputs["source_transcript_ref"] = pack._state.current_transcript_ref
        pack._pre_apply_blocking_count = pack._iter_blocking_count
        pack._pre_apply_blocking_signature = pack._iter_blocking_signature
        pack._awaiting_apply_outcome = True
        pack._pending_lineage_meta = {
            "iteration": iterations,
            "focus_key": focus_key,
            "summary": str(payload.get("reason") or "")[:120],
        }
        if not context.loop_memory.pending_refresh:
            pack._state.apply_reaudit_baseline_blocking_count = pack._iter_blocking_count
            pack._state.apply_reaudit_baseline_blocking_signature = pack._iter_blocking_signature
        return MoveExecutionPlan(
            action_type=TX_APPLY_EDIT_PLAN,
            action_inputs=inputs,
            idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, inputs),
        )

    return compile_transcript_edit_execution_support(
        pack,
        context,
        move_decision,
        idempotency_prefix=idempotency_prefix,
    )
