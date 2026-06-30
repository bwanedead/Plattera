"""Orchestrator hooks for agent-authored ``hydrate_next`` requests.

Two hooks, both mechanical:

* :func:`capture_hydrate_next_after_step` runs after an action executes (or
  is skipped).  It resolves ``@result.*`` placeholders against the just-
  completed tool result and stashes a bounded record on
  ``loop_memory.continuity.pending_agent_hydration`` so the next iteration
  can surface it.

* :func:`surface_pending_hydration_before_choose_action` runs at the top of
  the next iteration.  If a pending record exists and has not yet been
  hydrated, it dispatches a single bounded ``hydrate_artifact_refs`` step
  via the session manager, attaches the result to the record, and flips
  status to ``"surfaced"`` so the prompt projection layer can include it in
  the next prompt exactly once.

* :func:`clear_surfaced_hydration` drops a record once it has been surfaced
  so it does not loop forever.

None of these hooks decide which refs matter — that is for the agent.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from ...execution.contracts import ExecutionState, ExecutionStepRequest
from ...execution.session import ExecutionSessionManager
from ..memory import LoopMemoryState
from .contracts import ActionPlan
from .action_sequence import build_sequence_results_snapshot, effective_actions
from .hydrate_next import (
    HYDRATE_ARTIFACT_REFS_ACTION_ID,
    build_hydrate_next_record,
    build_tool_result_snapshot,
    enrich_hydrate_next_resolution_errors,
    resolve_hydrate_next_refs,
)
from .orchestrator_turn import accumulate_image_evidence

_LOG = logging.getLogger(__name__)


def capture_hydrate_next_after_step(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    step_result: Any | None,
    iteration: int,
) -> None:
    """Persist a bounded ``pending_agent_hydration`` record if authored.

    ``step_result`` is the orchestrator's ``ExecutionStepResult`` from the
    just-executed turn (or ``None`` for no-dispatch turns).  Placeholder
    resolution uses the result's ``outputs`` and ``artifact_refs``; for no-
    dispatch turns only literal refs resolve and placeholders produce errors.
    """
    if not action_plan.hydrate_next:
        return

    tool_snapshot = None
    record = getattr(step_result, "record", None) if step_result is not None else None
    if record is not None:
        result = getattr(record, "result", None)
        if result is not None:
            tool_snapshot = build_tool_result_snapshot(
                outputs=getattr(result, "outputs", None),
                artifact_refs=getattr(result, "artifact_refs", None),
            )

    batch_snapshot = None
    if len(effective_actions(action_plan)) > 1 or any(
        str(ref).startswith("@batch.") for ref in action_plan.hydrate_next
    ):
        batch_snapshot = build_sequence_results_snapshot(
            loop_memory.continuity.recent_action_sequence_result,
        )

    requested = list(action_plan.hydrate_next)
    resolved, errors = resolve_hydrate_next_refs(
        requested,
        tool_result=tool_snapshot,
        batch_results=batch_snapshot,
    )
    source_action_type = None
    tool_outputs = None
    if record is not None:
        source_action_type = str(getattr(record, "action_type", None) or "").strip() or None
        result = getattr(record, "result", None)
        if result is not None:
            raw_outputs = getattr(result, "outputs", None)
            tool_outputs = raw_outputs if isinstance(raw_outputs, Mapping) else None
    errors = enrich_hydrate_next_resolution_errors(
        errors,
        source_action_type=source_action_type,
        tool_outputs=tool_outputs,
    )
    record_payload = build_hydrate_next_record(
        requested_refs=requested,
        resolved_refs=resolved,
        reason=action_plan.hydrate_next_reason,
        errors=errors,
        source_turn_index=iteration,
    )
    loop_memory.continuity.pending_agent_hydration = record_payload


def surface_pending_hydration_before_choose_action(
    *,
    loop_memory: LoopMemoryState,
    session_manager: ExecutionSessionManager,
    session_id: str,
    request_id_prefix: str,
    run_id: str,
    iteration: int,
) -> None:
    """Dispatch a bounded hydration step for the pending record (idempotent).

    Skips when no record exists, when the record was already surfaced (flips
    nothing further — the prompt builder still shows it once on the surface
    iteration, and ``clear_surfaced_hydration`` drops it afterward), or when
    the record has no resolved refs to hydrate (still flipped to surfaced so
    the agent sees the compact error context).
    """
    record = loop_memory.continuity.pending_agent_hydration
    if not record:
        return
    status = str(record.get("status") or "pending")
    if status != "pending":
        return

    resolved = list(record.get("resolved_refs") or [])
    already_hydrated = record.get("hydrated_results") is not None
    if resolved and not already_hydrated:
        idem = f"{request_id_prefix}:iter:{int(iteration)}:agent_hydrate_next"
        req = ExecutionStepRequest(
            session_id=session_id,
            action_id=HYDRATE_ARTIFACT_REFS_ACTION_ID,
            inputs={"ref_ids": resolved},
            idempotency_key=idem,
            run_id=run_id or None,
        )
        try:
            step_result = session_manager.step(req)
        except Exception:  # noqa: BLE001 — surface compact failure, do not crash run
            _LOG.warning("agent_hydrate_next_dispatch_failed", exc_info=True)
            record["hydration_errors"] = [
                {"reason_code": "hydration_dispatch_exception"}
            ]
        else:
            _attach_hydration_result(record, step_result)
            # Funnel any image evidence from the hidden hydrate step into the
            # per-iteration buffer so the next model turn actually receives
            # the pixels, not just JSON metadata.  Mirrors the wiring normal
            # tool dispatch performs in ``orchestrator.py``.
            accumulate_image_evidence(
                loop_memory=loop_memory, step_result=step_result,
            )

    record["status"] = "surfaced"
    record["surfaced_iteration"] = int(iteration)


def clear_surfaced_hydration(*, loop_memory: LoopMemoryState) -> None:
    """Drop a record once it has been surfaced so it does not loop forever."""
    record = loop_memory.continuity.pending_agent_hydration
    if not record:
        return
    if str(record.get("status") or "") == "surfaced":
        loop_memory.continuity.pending_agent_hydration = None


def _attach_hydration_result(record: dict[str, Any], step_result: Any) -> None:
    """Copy ``outputs.results`` / ``outputs.errors`` (or refusal) into record."""
    execution_state = getattr(step_result, "execution_state", None)
    if execution_state != ExecutionState.EXECUTED:
        refusal = getattr(step_result, "refusal", None)
        record["hydration_errors"] = [
            {"reason_code": getattr(refusal, "reason_code", None) or "hydration_refused"}
        ]
        return
    record_inner = getattr(step_result, "record", None)
    result = getattr(record_inner, "result", None) if record_inner is not None else None
    outputs = getattr(result, "outputs", None) if result is not None else None
    if isinstance(outputs, dict):
        results_payload = outputs.get("results")
        errors_payload = outputs.get("errors")
        record["hydrated_results"] = (
            list(results_payload) if isinstance(results_payload, list) else []
        )
        if isinstance(errors_payload, list) and errors_payload:
            record["hydration_errors"] = list(errors_payload)
    else:
        record["hydrated_results"] = []
