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

_ALLOWED_HYDRATE_T0_KEYS = frozenset({"dossier_id", "transcription_id", "ref_ids", "max_refs"})


def _refusal_invalid_ref_container(field: str, value: Any) -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {
            "reason_code": "transcript_edit_input_conflict",
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": "invalid_ref_container_type",
                "message": f"{field} must be a JSON array (list/tuple) of string ref ids, or null.",
                "field": field,
                "got_type": type(value).__name__,
            }
        },
    }


def _refusal_invalid_ref_element(field: str, index: int, item: Any) -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {
            "reason_code": "transcript_edit_input_conflict",
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": "invalid_ref_id_element_type",
                "message": f"{field}[{index}] must be a string (t0:raw:<stem> ref id).",
                "field": field,
                "index": index,
                "got_type": type(item).__name__,
            }
        },
    }


def _parse_ref_id_container(field: str, value: Any) -> tuple[list[str] | None, dict[str, Any] | None]:
    """Parse ``ref_ids`` / ``t0_raw_ref_ids``: ``null`` or list/tuple of strings only (no coercion)."""
    if value is None:
        return [], None
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                return None, _refusal_invalid_ref_element(field, index, item)
            stripped = item.strip()
            if stripped:
                out.append(stripped)
        return out, None
    return None, _refusal_invalid_ref_container(field, value)


def _ref_id_multisets_equal(a: list[str], b: list[str]) -> bool:
    return sorted(a) == sorted(b)


def _prepare_hydrate_t0_inputs(raw: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Merge ``ref_ids`` / ``t0_raw_ref_ids`` (alias). Returns ``(inputs, refusal)``; refusal is set on conflict."""
    data = dict(raw)
    has_ref = "ref_ids" in data
    has_alias = "t0_raw_ref_ids" in data

    if has_ref:
        ref_norm, err = _parse_ref_id_container("ref_ids", data["ref_ids"])
        if err is not None:
            return data, err
    else:
        ref_norm = None

    if has_alias:
        alias_norm, err = _parse_ref_id_container("t0_raw_ref_ids", data["t0_raw_ref_ids"])
        if err is not None:
            return data, err
    else:
        alias_norm = None

    if has_ref and has_alias:
        if not _ref_id_multisets_equal(list(ref_norm or []), list(alias_norm or [])):
            return data, {
                "executed": False,
                "refusal": {
                    "reason_code": "transcript_edit_input_conflict",
                    "retryable": False,
                    "blocked_by_invariant": True,
                    "blocked_by_budget": False,
                    "missing_inputs": [],
                },
                "outputs": {
                    "error": {
                        "code": "ref_ids_t0_raw_ref_ids_conflict",
                        "message": "ref_ids and t0_raw_ref_ids were both provided but do not list the same refs.",
                        "ref_ids": list(ref_norm or []),
                        "t0_raw_ref_ids": list(alias_norm or []),
                    }
                },
            }
        data.pop("t0_raw_ref_ids", None)
        data["ref_ids"] = list(ref_norm or [])
    elif has_alias and not has_ref:
        data["ref_ids"] = list(alias_norm or [])
        data.pop("t0_raw_ref_ids", None)
    elif has_ref:
        data["ref_ids"] = list(ref_norm or [])
        data.pop("t0_raw_ref_ids", None)

    return data, None


def _filter_hydrate_t0_kwargs(data: Mapping[str, Any]) -> dict[str, Any]:
    return {k: data[k] for k in _ALLOWED_HYDRATE_T0_KEYS if k in data}


def _hydrate_t0_draft_refs_handler(request: Any) -> Any:
    inputs = dict(_tool_request_inputs(request))
    prepared, refusal = _prepare_hydrate_t0_inputs(inputs)
    if refusal is not None:
        return refusal
    kwargs = _filter_hydrate_t0_kwargs(prepared)
    try:
        raw_result = hydrate_t0_draft_refs(**kwargs)
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


def _tool_handler_entries() -> tuple[tuple[str, Callable[[Any], Any]], ...]:
    return (
        ("load_transcript_edit_startup_inventory", _tool_handler_passthrough(build_transcript_edit_startup_inventory)),
        ("hydrate_t0_draft_refs", _hydrate_t0_draft_refs_handler),
        ("hydrate_transcript_edit_working_draft", _tool_handler_passthrough(hydrate_transcript_edit_working_draft)),
        ("load_source_image_context", _tool_handler_passthrough(hydrate_source_image_context)),
        ("save_transcript_edit", _tool_handler_passthrough(save_transcript_edit)),
        ("publish_transcript_edit_output", _tool_handler_passthrough(publish_transcript_edit_output)),
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
        ToolBinding(tool_id=tool_id, handler=handler)
        for tool_id, handler in _tool_handler_entries()
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
