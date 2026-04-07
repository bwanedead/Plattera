"""Generic action dispatch executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .action_ids import normalize_action_id
from .contracts import ActionDispatchHandler, ActionDispatchResult, ExecutionRefusal, ExecutionStepRequest


@dataclass
class ExecutionExecutor:
    handlers: dict[str, ActionDispatchHandler] = field(default_factory=dict)

    def register(self, action_id: str, handler: ActionDispatchHandler) -> None:
        self.handlers[normalize_action_id(action_id)] = handler

    def execute(self, request: ExecutionStepRequest) -> ActionDispatchResult:
        action_id = normalize_action_id(request.action_id)
        normalized_request = ExecutionStepRequest(
            session_id=request.session_id,
            action_id=action_id,
            inputs=dict(request.inputs),
            idempotency_key=str(request.idempotency_key or "").strip(),
            run_id=request.run_id,
        )

        handler = self.handlers.get(action_id)
        if handler is None:
            return ActionDispatchResult(
                action_id=action_id,
                executed=False,
                reason_codes=("action_not_registered",),
                refusal=ExecutionRefusal(reason_code="action_not_registered", retryable=False),
                idempotency_key=normalized_request.idempotency_key,
            )

        raw_result = handler(normalized_request)
        return _coerce_result(raw_result, action_id=action_id, idempotency_key=normalized_request.idempotency_key)


def _coerce_result(
    raw_result: ActionDispatchResult | Mapping[str, Any],
    *,
    action_id: str,
    idempotency_key: str,
) -> ActionDispatchResult:
    if isinstance(raw_result, ActionDispatchResult):
        return raw_result
    if not isinstance(raw_result, Mapping):
        return ActionDispatchResult(
            action_id=action_id,
            executed=False,
            reason_codes=("invalid_action_result",),
            refusal=ExecutionRefusal(reason_code="invalid_action_result", retryable=False),
            idempotency_key=idempotency_key,
        )
    refusal = raw_result.get("refusal")
    refusal_obj = None
    if isinstance(refusal, Mapping):
        refusal_obj = ExecutionRefusal(
            reason_code=str(refusal.get("reason_code") or "refused"),
            retryable=bool(refusal.get("retryable", False)),
            blocked_by_budget=bool(refusal.get("blocked_by_budget", False)),
            blocked_by_invariant=bool(refusal.get("blocked_by_invariant", False)),
            missing_inputs=tuple(str(item) for item in list(refusal.get("missing_inputs") or []) if str(item).strip()),
        )
    outputs = raw_result.get("outputs")
    if not isinstance(outputs, dict):
        outputs = {}
    raw_evidence = raw_result.get("image_evidence")
    image_evidence: tuple[dict[str, Any], ...] = ()
    if isinstance(raw_evidence, (list, tuple)):
        image_evidence = tuple(e for e in raw_evidence if isinstance(e, dict))
    return ActionDispatchResult(
        action_id=action_id,
        executed=bool(raw_result.get("executed", True)),
        reason_codes=tuple(str(item) for item in list(raw_result.get("reason_codes") or []) if str(item).strip()),
        outputs=dict(outputs),
        refusal=refusal_obj,
        artifact_refs=tuple(str(item) for item in list(raw_result.get("artifact_refs") or []) if str(item).strip()),
        idempotency_key=idempotency_key,
        image_evidence=image_evidence,
    )
