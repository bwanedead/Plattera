"""Mechanical transcript-edit to harness composition translation.

This seam is intentionally narrow: it packages authored prompt blocks,
opaque startup inventory payloads, and tool-id bindings into generic harness
turn surfaces without taking on orchestration or closure semantics.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from collections.abc import Mapping
from typing import Any, Callable, Sequence

from harness.runtime.composition import ToolBinding, TurnBlock, TurnSurface
from ..execution.tool_specs import build_transcript_edit_tool_specs
from tooling.mapping.transcript_edit import (
    build_transcript_edit_startup_inventory,
    hydrate_source_image_context,
    hydrate_t0_draft_refs,
    hydrate_transcript_edit_working_draft,
    publish_transcript_edit_output,
    save_transcript_edit,
)

from ..payloads import TranscriptEditStartupInventory
from ..prompting import PromptBlock

TRANSCRIPT_EDIT_RUNTIME_SURFACE_ID = "transcript_edit"
_PROMPT_BLOCK_NAMESPACE = "transcript_edit.prompt_block"
_PAYLOAD_NAMESPACE = "transcript_edit"


def _tool_handler_passthrough(tool_fn: Callable[..., Any]) -> Callable[[Any], Any]:
    def handler(request: Any) -> Any:
        inputs = _tool_request_inputs(request)
        try:
            raw_result = tool_fn(**dict(inputs))
        except Exception as exc:
            return {
                "executed": False,
                "refusal": {
                    "reason_code": "transcript_edit_tool_error",
                    "retryable": False,
                },
                "outputs": {
                    "error": str(exc),
                },
            }
        return _normalize_tool_result(raw_result)

    return handler


def _tool_request_inputs(request: Any) -> Mapping[str, Any]:
    if isinstance(request, Mapping):
        return request
    inputs = getattr(request, "inputs", None)
    if isinstance(inputs, Mapping):
        return inputs
    raise TypeError("tool_request_inputs_must_be_mapping")


def _tool_handler_specs() -> tuple[tuple[str, Callable[..., Any]], ...]:
    return (
        ("load_transcript_edit_startup_inventory", build_transcript_edit_startup_inventory),
        ("hydrate_t0_draft_refs", hydrate_t0_draft_refs),
        ("hydrate_transcript_edit_working_draft", hydrate_transcript_edit_working_draft),
        ("load_source_image_context", hydrate_source_image_context),
        ("save_transcript_edit", save_transcript_edit),
        ("publish_transcript_edit_output", publish_transcript_edit_output),
    )


def _build_turn_blocks(prompt_blocks: Sequence[PromptBlock]) -> tuple[TurnBlock, ...]:
    return tuple(
        TurnBlock(
            content=block.text,
            metadata={
                _PROMPT_BLOCK_NAMESPACE: asdict(block),
            },
        )
        for block in prompt_blocks
    )


def build_transcript_edit_tool_bindings() -> tuple[ToolBinding, ...]:
    """Bind implemented transcript-edit tooling by opaque tool id only."""

    return tuple(
        ToolBinding(tool_id=tool_id, handler=_tool_handler_passthrough(tool_fn))
        for tool_id, tool_fn in _tool_handler_specs()
    )


def build_transcript_edit_turn_surface(
    *,
    prompt_blocks: Sequence[PromptBlock],
    startup_inventory: TranscriptEditStartupInventory,
) -> TurnSurface:
    """Package transcript-edit prompt blocks, inventory payload, and bindings."""

    tool_bindings = build_transcript_edit_tool_bindings()
    return TurnSurface(
        surface_id=TRANSCRIPT_EDIT_RUNTIME_SURFACE_ID,
        blocks=_build_turn_blocks(prompt_blocks),
        payload={
            _PAYLOAD_NAMESPACE: {
                "startup_inventory": asdict(startup_inventory),
                "tool_specs": _build_tool_specs(),
                "tool_ids": [binding.tool_id for binding in tool_bindings],
            },
        },
        tool_bindings=tool_bindings,
    )


def _build_tool_specs() -> tuple[dict[str, Any], ...]:
    return tuple(asdict(spec) for spec in build_transcript_edit_tool_specs())


def _normalize_tool_result(raw_result: Any) -> Any:
    if isinstance(raw_result, Mapping):
        if _looks_like_action_result(raw_result):
            return dict(raw_result)
        return {
            "executed": True,
            "outputs": {
                "result": _jsonable(raw_result),
            },
        }
    if is_dataclass(raw_result):
        return {
            "executed": True,
            "outputs": {
                "result": _jsonable(asdict(raw_result)),
            },
        }
    if hasattr(raw_result, "model_dump"):
        dumped = raw_result.model_dump(mode="python")  # type: ignore[call-arg]
        return {
            "executed": True,
            "outputs": {
                "result": _jsonable(dumped),
            },
        }
    return {
        "executed": True,
        "outputs": {
            "result": _jsonable(raw_result),
        },
    }


def _looks_like_action_result(value: Mapping[str, Any]) -> bool:
    return any(key in value for key in ("executed", "outputs", "refusal", "reason_codes", "artifact_refs"))


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="python")  # type: ignore[call-arg]
        return _jsonable(dumped)
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(raw_value) for key, raw_value in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=str)]
    return value
