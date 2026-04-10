"""Prompt-visible sanitization helpers for the kernel choose-action envelope.

Extracted from ``llm_prompt_builder`` to keep envelope assembly focused.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..composition import ComposedTurnInput
from .contracts import SharedStateProjection
from .prompt_utils import jsonable

_PROJECTION_OPAQUE_KEYS_STRIPPED_FROM_PROMPT = frozenset({"launch_context", "turn_snapshot"})


def projection_document(projection: SharedStateProjection | None) -> dict[str, Any]:
    if projection is None:
        return {}
    return {
        "mission_state": prompt_visible_projection_state(projection.mission_state),
        "resolution_state": prompt_visible_projection_state(projection.resolution_state),
        "latest_refs": dict(projection.latest_refs),
        "active_item_id": projection.active_item_id,
    }


def turn_input_document(composed_input: ComposedTurnInput) -> dict[str, Any]:
    return {
        "blocks": [
            {"content": block.content, "metadata": prompt_visible_block_metadata(block.metadata)}
            for block in composed_input.blocks
        ],
        "surface_payloads": prompt_visible_surface_payloads(composed_input.surface_payloads),
        "tool_ids": list(composed_input.tool_handlers.keys()),
    }


def prompt_visible_projection_state(state: Any) -> Any:
    return _strip_projection_opaque_duplicates(jsonable(state))


def prompt_visible_block_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    payload = jsonable(metadata)
    if not isinstance(payload, dict):
        return {}
    return payload


def prompt_visible_surface_payloads(surface_payloads: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    visible: dict[str, Any] = {}
    for surface_id, payload in surface_payloads.items():
        visible[str(surface_id)] = prompt_visible_payload_node(jsonable(payload))
    return visible


def prompt_visible_payload_node(value: Any) -> Any:
    if isinstance(value, list):
        return [prompt_visible_payload_node(item) for item in value]
    if not isinstance(value, dict):
        return value

    if {"tool_id", "category", "purpose", "expected_request_shape"}.issubset(value.keys()):
        return {
            "tool_id": value.get("tool_id"),
            "category": value.get("category"),
            "purpose": value.get("purpose"),
            "expected_request_shape": value.get("expected_request_shape"),
        }

    filtered: dict[str, Any] = {}
    for key, raw in value.items():
        skey = str(key)
        if skey in {"tool_ids", "closure_policy"}:
            continue
        filtered[skey] = prompt_visible_payload_node(raw)
    return filtered


def _strip_projection_opaque_duplicates(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_projection_opaque_duplicates(item) for item in value]
    if not isinstance(value, dict):
        return value

    filtered: dict[str, Any] = {}
    for key, raw in value.items():
        skey = str(key)
        if skey == "opaque_payload" and isinstance(raw, dict):
            filtered[skey] = {
                str(inner_key): _strip_projection_opaque_duplicates(inner_value)
                for inner_key, inner_value in raw.items()
                if str(inner_key) not in _PROJECTION_OPAQUE_KEYS_STRIPPED_FROM_PROMPT
            }
            continue
        filtered[skey] = _strip_projection_opaque_duplicates(raw)
    return filtered
