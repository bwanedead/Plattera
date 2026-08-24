"""Bounded, generic tool-contract projection for slim recovery prompts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

_MAX_TOOL_CONTRACTS = 48
_MAX_REQUEST_SHAPE_CHARS = 320
_MAX_REQUEST_SHAPE_PREVIEW_CHARS = 160
_MAX_WALK_DEPTH = 8
_MAX_NODES = 2_000


def project_compact_tool_contracts(
    surface_payloads: Mapping[str, Any] | None,
    *,
    available_tool_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Project prompt-visible compact tool contracts from composed surface payloads.

    Includes ``tool_id``, whole ``expected_request_shape`` when it fits the bound, or an
    explicit omission/preview with original character count when oversized, plus batching
    fields when already present on surface ``tool_specs`` rows. Does not invent domain doctrine.
    """
    if not isinstance(surface_payloads, Mapping) or not surface_payloads:
        return []
    allow = {str(tool_id) for tool_id in (available_tool_ids or ()) if str(tool_id).strip()}
    collected: dict[str, dict[str, Any]] = {}
    _walk_for_tool_specs(surface_payloads, collected=collected, allow=allow, depth=0, nodes_left=[_MAX_NODES])
    ordered_ids = sorted(collected)
    return [collected[tool_id] for tool_id in ordered_ids[:_MAX_TOOL_CONTRACTS]]


def _walk_for_tool_specs(
    node: Any,
    *,
    collected: dict[str, dict[str, Any]],
    allow: set[str],
    depth: int,
    nodes_left: list[int],
) -> None:
    if nodes_left[0] <= 0 or depth > _MAX_WALK_DEPTH:
        return
    nodes_left[0] -= 1
    if isinstance(node, Mapping):
        specs = node.get("tool_specs")
        if isinstance(specs, list):
            for row in specs:
                if nodes_left[0] <= 0:
                    return
                nodes_left[0] -= 1
                contract = _compact_contract_from_spec_row(row)
                if contract is None:
                    continue
                tool_id = str(contract["tool_id"])
                if allow and tool_id not in allow:
                    continue
                collected.setdefault(tool_id, contract)
        for value in node.values():
            if len(collected) >= _MAX_TOOL_CONTRACTS:
                return
            _walk_for_tool_specs(
                value,
                collected=collected,
                allow=allow,
                depth=depth + 1,
                nodes_left=nodes_left,
            )
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            if len(collected) >= _MAX_TOOL_CONTRACTS or nodes_left[0] <= 0:
                return
            _walk_for_tool_specs(
                item,
                collected=collected,
                allow=allow,
                depth=depth + 1,
                nodes_left=nodes_left,
            )


def _compact_contract_from_spec_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, Mapping):
        return None
    tool_id = row.get("tool_id")
    if type(tool_id) is not str:
        return None
    tool_id = tool_id.strip()
    if not tool_id or len(tool_id) > 120:
        return None
    shape = row.get("expected_request_shape")
    if type(shape) is not str:
        return None
    shape = shape.strip()
    if not shape:
        return None
    contract: dict[str, Any] = {"tool_id": tool_id}
    _attach_request_shape(contract, shape)
    batching = _compact_batching(row.get("batching"))
    if batching is not None:
        contract["batching"] = batching
    return contract


def _attach_request_shape(contract: dict[str, Any], shape: str) -> None:
    """Attach request-shape evidence without silently truncating mid-value.

    Whole shape fits under ``expected_request_shape``. Oversized shapes omit that key
    and instead surface an explicit preview plus original character count.
    """
    if len(shape) <= _MAX_REQUEST_SHAPE_CHARS:
        contract["expected_request_shape"] = shape
        return
    preview = shape[:_MAX_REQUEST_SHAPE_PREVIEW_CHARS]
    contract["expected_request_shape_omitted"] = True
    contract["expected_request_shape_char_count"] = len(shape)
    contract["expected_request_shape_preview"] = f"{preview}...[omitted]"


def _compact_batching(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    out: dict[str, Any] = {}
    allowed = value.get("allowed")
    if type(allowed) is bool:
        out["allowed"] = allowed
    max_calls = value.get("max_calls_per_batch")
    if type(max_calls) is int and 0 <= max_calls <= 1_000_000:
        out["max_calls_per_batch"] = max_calls
    side_effect = value.get("side_effect_class")
    if type(side_effect) is str:
        text = side_effect.strip()
        if text and len(text) <= 64:
            out["side_effect_class"] = text
    can_parallel = value.get("can_run_parallel")
    if type(can_parallel) is bool:
        out["can_run_parallel"] = can_parallel
    return out or None
