"""JSON-safe wire forms for execution contracts (resume / persistence; mechanical only)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .action_ids import normalize_action_id
from .contracts import ActionDispatchResult, ExecutionRefusal, ExecutionStepRequest


def execution_refusal_to_wire(r: ExecutionRefusal) -> dict[str, Any]:
    return {
        "reason_code": r.reason_code,
        "retryable": r.retryable,
        "blocked_by_budget": r.blocked_by_budget,
        "blocked_by_invariant": r.blocked_by_invariant,
        "missing_inputs": list(r.missing_inputs),
    }


def execution_refusal_from_wire(raw: object) -> ExecutionRefusal | None:
    if not isinstance(raw, Mapping):
        return None
    rc = str(raw.get("reason_code") or "").strip()
    if not rc:
        return None
    return ExecutionRefusal(
        reason_code=rc,
        retryable=bool(raw.get("retryable", False)),
        blocked_by_budget=bool(raw.get("blocked_by_budget", False)),
        blocked_by_invariant=bool(raw.get("blocked_by_invariant", False)),
        missing_inputs=tuple(str(x) for x in list(raw.get("missing_inputs") or []) if str(x).strip()),
    )


def execution_step_request_to_wire(req: ExecutionStepRequest) -> dict[str, Any]:
    return {
        "session_id": req.session_id,
        "action_id": str(req.action_id),
        "inputs": dict(req.inputs),
        "idempotency_key": req.idempotency_key,
        "run_id": req.run_id,
    }


def execution_step_request_from_wire(raw: object) -> ExecutionStepRequest | None:
    if not isinstance(raw, Mapping):
        return None
    try:
        aid = normalize_action_id(raw.get("action_id"))
    except ValueError:
        return None
    sid = str(raw.get("session_id") or "").strip()
    if not sid:
        return None
    run_id = raw.get("run_id")
    return ExecutionStepRequest(
        session_id=sid,
        action_id=aid,
        inputs=dict(raw.get("inputs") or {}) if isinstance(raw.get("inputs"), Mapping) else {},
        idempotency_key=str(raw.get("idempotency_key") or ""),
        run_id=str(run_id).strip() if run_id is not None and str(run_id).strip() else None,
    )


def action_dispatch_result_to_wire(res: ActionDispatchResult) -> dict[str, Any]:
    return {
        "action_id": str(res.action_id),
        "executed": res.executed,
        "reason_codes": list(res.reason_codes),
        "outputs": dict(res.outputs),
        "refusal": execution_refusal_to_wire(res.refusal) if res.refusal is not None else None,
        "artifact_refs": list(res.artifact_refs),
        "idempotency_key": res.idempotency_key,
    }


def action_dispatch_result_from_wire(raw: object) -> ActionDispatchResult | None:
    if not isinstance(raw, Mapping):
        return None
    try:
        aid = normalize_action_id(raw.get("action_id"))
    except ValueError:
        return None
    refusal_raw = raw.get("refusal")
    refusal = execution_refusal_from_wire(refusal_raw) if refusal_raw is not None else None
    return ActionDispatchResult(
        action_id=aid,
        executed=bool(raw.get("executed", False)),
        reason_codes=tuple(str(x) for x in list(raw.get("reason_codes") or []) if str(x).strip()),
        outputs=dict(raw.get("outputs") or {}) if isinstance(raw.get("outputs"), Mapping) else {},
        refusal=refusal,
        artifact_refs=tuple(str(x) for x in list(raw.get("artifact_refs") or []) if str(x).strip()),
        idempotency_key=str(raw.get("idempotency_key") or ""),
    )
