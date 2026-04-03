"""Generic LLM-backed orchestration adapter for composed turn surfaces.

This module stays blind to domain semantics. It packages opaque turn-surface
data into a generic prompt envelope, asks a text model for one JSON action
plan, and validates that the result is mechanically coherent.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..composition import ComposedTurnInput
from ...mission_state import new_mission_state, new_resolution_state
from .contracts import ActionPlan, OrchestrationAdapter, OrchestratorContext, SharedStateProjection

TextModelCaller = Callable[..., Mapping[str, Any] | str]

_ALLOWED_ACTION_PLAN_KEYS = {
    "action_type",
    "action_inputs",
    "idempotency_key",
    "skip_execution",
    "wait_for_human",
    "complete_run",
    "rationale",
}


class ModelActionParseError(ValueError):
    """Raised when the model output cannot be mechanically parsed into an action plan."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class LlmTurnOrchestrationAdapter(OrchestrationAdapter):
    composed_input: ComposedTurnInput
    text_model_caller: TextModelCaller
    model_name: str
    opaque_launch_context: Mapping[str, Any] = field(default_factory=dict)

    def initialize(self, context: OrchestratorContext) -> None:
        del context

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        turn_snapshot = _turn_snapshot(self.composed_input)
        mission_state = new_mission_state(
            mission_id=context.session_id,
            loop_family="orchestration_kernel",
            session_id=context.session_id,
            request_id=context.request_id_prefix,
            opaque_payload={
                "launch_context": _jsonable(self.opaque_launch_context),
                "turn_snapshot": turn_snapshot,
            },
        )
        resolution_state = new_resolution_state(
            opaque_payload={
                "turn_snapshot": turn_snapshot,
            }
        )
        return SharedStateProjection(
            mission_state=mission_state,
            resolution_state=resolution_state,
            latest_refs=dict(context.loop_memory.continuity.latest_refs),
            active_item_id=context.loop_memory.continuity.active_item_id,
        )

    def choose_action(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
    ) -> ActionPlan:
        prompt = _build_prompt(
            composed_input=self.composed_input,
            opaque_launch_context=self.opaque_launch_context,
            context=context,
            projection=projection,
        )
        raw_response = self.text_model_caller(prompt, self.model_name)
        return _coerce_action_plan(raw_response, available_tool_ids=tuple(self.composed_input.tool_handlers.keys()))

    def evaluate_terminal(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
    ):
        del context, projection
        return None


def _build_prompt(
    *,
    composed_input: ComposedTurnInput,
    opaque_launch_context: Mapping[str, Any],
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
) -> str:
    envelope = {
        "iteration": context.loop_memory.iterations,
        "session_id": context.session_id,
        "request_id_prefix": context.request_id_prefix,
        "launch_context": _jsonable(opaque_launch_context),
        "turn_input": _turn_input_document(composed_input),
        "latest_refs": dict(context.loop_memory.continuity.latest_refs),
        "active_item_id": context.loop_memory.continuity.active_item_id,
        "projection": _projection_document(projection),
    }
    instruction = (
        "Return exactly one JSON object matching this schema:\n"
        "{"
        '"action_type": string|null, '
        '"action_inputs": object, '
        '"idempotency_key": string, '
        '"skip_execution": boolean, '
        '"wait_for_human": boolean, '
        '"complete_run": boolean, '
        '"rationale": string|null'
        "}\n"
        "Choose action_type only from the provided tool_ids unless complete_run or wait_for_human is true.\n"
        "Do not wrap the JSON in markdown and do not add commentary."
    )
    return instruction + "\n\n" + json.dumps(envelope, ensure_ascii=False, sort_keys=True)


def _coerce_action_plan(raw_response: Mapping[str, Any] | str, *, available_tool_ids: tuple[str, ...]) -> ActionPlan:
    text = _extract_text(raw_response)
    try:
        payload = json.loads(text)
    except Exception as exc:
        raise ModelActionParseError("invalid_model_action_json", "model output was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ModelActionParseError("invalid_model_action_json", "model output must be a JSON object")

    unknown_keys = sorted(set(payload.keys()) - _ALLOWED_ACTION_PLAN_KEYS)
    if unknown_keys:
        raise ModelActionParseError(
            "invalid_model_action_json",
            f"unexpected action plan keys: {', '.join(unknown_keys)}",
        )

    action_type = _optional_text(payload.get("action_type"))
    action_inputs = payload.get("action_inputs")
    if action_inputs is None:
        action_inputs = {}
    if not isinstance(action_inputs, Mapping):
        raise ModelActionParseError("invalid_model_action_json", "action_inputs must be an object")

    complete_run = _require_json_bool(payload, "complete_run")
    wait_for_human = _require_json_bool(payload, "wait_for_human")
    skip_execution = _require_json_bool(payload, "skip_execution")

    if complete_run and wait_for_human:
        raise ModelActionParseError("invalid_model_action_json", "complete_run and wait_for_human are mutually exclusive")

    if not complete_run and not wait_for_human:
        if not action_type:
            raise ModelActionParseError("invalid_model_action_json", "action_type is required unless completing or waiting")
        if available_tool_ids and action_type not in available_tool_ids:
            raise ModelActionParseError("invalid_model_action_json", f"unknown action_type: {action_type}")

    return ActionPlan(
        action_type=action_type or None,
        action_inputs=dict(action_inputs),
        idempotency_key=_optional_text(payload.get("idempotency_key")) or "",
        skip_execution=skip_execution,
        wait_for_human=wait_for_human,
        complete_run=complete_run,
        rationale=_optional_text(payload.get("rationale")),
    )


def _extract_text(raw_response: Mapping[str, Any] | str) -> str:
    if isinstance(raw_response, str):
        text = raw_response.strip()
        if not text:
            raise ModelActionParseError("invalid_model_action_json", "model output was empty")
        return text
    if raw_response.get("success") is False:
        raise ModelActionParseError(
            "model_call_failed",
            str(raw_response.get("error") or "model caller reported failure"),
        )
    for key in ("text", "content", "output_text"):
        value = raw_response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ModelActionParseError("invalid_model_action_json", "model caller did not return text")


def _projection_document(projection: SharedStateProjection | None) -> dict[str, Any]:
    if projection is None:
        return {}
    return {
        "mission_state": _jsonable(projection.mission_state),
        "resolution_state": _jsonable(projection.resolution_state),
        "latest_refs": dict(projection.latest_refs),
        "active_item_id": projection.active_item_id,
    }


def _turn_input_document(composed_input: ComposedTurnInput) -> dict[str, Any]:
    return {
        "blocks": [
            {
                "content": block.content,
                "metadata": _jsonable(block.metadata),
            }
            for block in composed_input.blocks
        ],
        "surface_payloads": {
            surface_id: _jsonable(payload)
            for surface_id, payload in composed_input.surface_payloads.items()
        },
        "tool_ids": list(composed_input.tool_handlers.keys()),
    }


def _turn_snapshot(composed_input: ComposedTurnInput) -> dict[str, Any]:
    return {
        "surface_payloads": {
            surface_id: _jsonable(payload)
            for surface_id, payload in composed_input.surface_payloads.items()
        },
        "tool_ids": list(composed_input.tool_handlers.keys()),
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="python")  # type: ignore[call-arg]
        return _jsonable(dumped)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(raw_value) for key, raw_value in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=str)]
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_json_bool(payload: Mapping[str, Any], key: str) -> bool:
    if key not in payload:
        raise ModelActionParseError("invalid_model_action_json", f"{key} is required and must be a boolean")
    value = payload.get(key)
    if type(value) is not bool:
        raise ModelActionParseError("invalid_model_action_json", f"{key} must be a JSON boolean")
    return value
