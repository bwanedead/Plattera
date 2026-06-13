"""Execution-layer handler factory for ``delegate_subtask``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ....execution.contracts import ActionDispatchResult, ExecutionRefusal, ExecutionStepRequest
from .contracts import DELEGATE_SUBTASK_ACTION_TYPE
from .errors import SubtaskValidationError
from .registry import DEFAULT_SUBTASK_REGISTRY, SubtaskProfileRegistry
from .runner import HydrationHandler, TextModelCaller, run_delegate_subtask
from .validation import validate_delegate_subtask_inputs


def make_delegate_subtask_handler(
    *,
    model_caller: TextModelCaller,
    model_name: str,
    hydration_handler: HydrationHandler | None,
    registry: SubtaskProfileRegistry = DEFAULT_SUBTASK_REGISTRY,
    llm_streaming: bool | None = None,
) -> Any:
    """Return an execution handler closed over model and hydration seams."""

    def handler(request: ExecutionStepRequest) -> ActionDispatchResult:
        inputs = dict(request.inputs) if isinstance(request.inputs, Mapping) else {}
        subtask_id = str(inputs.pop("_subtask_alias", "") or "").strip() or _fallback_subtask_id(request)
        try:
            subtask_request = validate_delegate_subtask_inputs(
                inputs,
                registry=registry,
                allow_private_keys=False,
            )
        except SubtaskValidationError as exc:
            return ActionDispatchResult(
                action_id=DELEGATE_SUBTASK_ACTION_TYPE,
                executed=False,
                reason_codes=(exc.reason_code,),
                refusal=ExecutionRefusal(reason_code=exc.reason_code, retryable=True),
                idempotency_key=request.idempotency_key,
            )
        profile = registry.require(subtask_request.profile)
        outputs = run_delegate_subtask(
            subtask_id=subtask_id,
            request=subtask_request,
            profile=profile,
            model_caller=model_caller,
            default_model_name=model_name,
            hydration_handler=hydration_handler,
            parent_request=request,
            llm_streaming=llm_streaming,
        )
        return ActionDispatchResult(
            action_id=DELEGATE_SUBTASK_ACTION_TYPE,
            executed=True,
            outputs=outputs,
            idempotency_key=request.idempotency_key,
        )

    return handler


def _fallback_subtask_id(request: ExecutionStepRequest) -> str:
    key = str(request.idempotency_key or "").strip()
    if key:
        return key.rsplit(":", 1)[-1]
    return DELEGATE_SUBTASK_ACTION_TYPE
