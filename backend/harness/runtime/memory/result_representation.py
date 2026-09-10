"""Generic exact / provider-view / unavailable result representation.

Shared mechanical selection for pending-result delivery (BR-017) and host
hydration lanes (hydrate_next + pinned-ref auto-hydration). Does not import
domain or tooling packages. Never prefix-truncates content.
"""

from __future__ import annotations

import json
import math
from typing import Any, Mapping

from harness.execution.agent_result_view import (
    MAX_AGENT_RESULT_VIEW_CHARS,
    OMISSION_REASON_INVALID_SHAPE,
    OMISSION_REASON_NOT_JSON_SAFE,
    OMISSION_REASON_UNSUPPORTED_SCHEMA_VERSION,
    OMISSION_REASON_VIEW_BUDGET,
    AgentResultView,
    agent_result_view_omission_from_wire,
    agent_result_view_omission_to_wire,
    agent_result_view_to_wire,
    normalize_agent_result_view_pair,
)

REPRESENTATION_EXACT_OUTPUTS = "exact_outputs"
REPRESENTATION_AGENT_RESULT_VIEW = "agent_result_view"
REPRESENTATION_UNAVAILABLE = "unavailable"

REASON_MISSING_VIEW = "missing_agent_result_view"
REASON_INVALID_VIEW = "invalid_agent_result_view"
REASON_LANE_BUDGET = "lane_budget"

MAX_DELIVERY_OUTPUT_KEYS = 32
MAX_OUTPUT_KEY_CHARS = 128

_HOST_OR_BINARY_KEYS = frozenset(
    {
        "path",
        "absolute_path",
        "host_path",
        "file_path",
        "workspace_root",
        "b64",
        "base64",
        "bytes",
        "binary",
        "image_bytes",
        "raw_image",
        "raw_image_data",
        "raw_prompt",
        "raw_prompt_text",
        "raw_llm_response",
        "raw_llm_response_text",
        "prompt_text",
    }
)
_BINARY_KEY_PARTS = ("b64", "base64", "bytes", "binary")

_ALLOWED_OMISSION_REASONS = frozenset(
    {
        OMISSION_REASON_INVALID_SHAPE,
        OMISSION_REASON_UNSUPPORTED_SCHEMA_VERSION,
        OMISSION_REASON_NOT_JSON_SAFE,
        OMISSION_REASON_VIEW_BUDGET,
    }
)
_ALLOWED_REPRESENTATION_KINDS = frozenset(
    {
        REPRESENTATION_EXACT_OUTPUTS,
        REPRESENTATION_AGENT_RESULT_VIEW,
        REPRESENTATION_UNAVAILABLE,
    }
)
_ALLOWED_UNAVAILABLE_KEYS = frozenset(
    {
        "reason",
        "observed_output_chars",
        "maximum_content_chars",
        "output_keys",
        "output_keys_omitted_count",
        "view_omission",
    }
)


def measure_compact_json_chars(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def is_json_safe(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and is_json_safe(v) for k, v in value.items())
    if isinstance(value, list):
        return all(is_json_safe(item) for item in value)
    return False


def contains_host_or_binary_fields(value: Any) -> bool:
    """True when any object key is a host path or binary/raw payload field."""
    if isinstance(value, Mapping):
        for key, inner in value.items():
            if not isinstance(key, str):
                return True
            lowered = key.lower()
            if lowered in _HOST_OR_BINARY_KEYS:
                return True
            if any(part in lowered for part in _BINARY_KEY_PARTS):
                return True
            if contains_host_or_binary_fields(inner):
                return True
        return False
    if isinstance(value, list):
        return any(contains_host_or_binary_fields(item) for item in value)
    return False


def select_result_representation(
    *,
    outputs: Mapping[str, Any] | dict[str, Any],
    view: AgentResultView | None,
    view_omission: Any,
    exact_outputs_eligible: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Choose exact_outputs, agent_result_view, or unavailable for one outputs blob.

    ``exact_outputs_eligible`` lets host hydration refuse exact transport when
    outputs contain host/path/binary fields without changing BR-017 precedence.
    """
    outputs_dict = dict(outputs) if isinstance(outputs, Mapping) else {}
    exact_ok = bool(exact_outputs_eligible) and is_json_safe(outputs_dict)
    if exact_ok:
        try:
            output_chars = measure_compact_json_chars(outputs_dict)
        except (TypeError, ValueError):
            exact_ok = False
            output_chars = MAX_AGENT_RESULT_VIEW_CHARS + 1
    else:
        try:
            output_chars = (
                measure_compact_json_chars(outputs_dict)
                if is_json_safe(outputs_dict)
                else MAX_AGENT_RESULT_VIEW_CHARS + 1
            )
        except (TypeError, ValueError):
            output_chars = MAX_AGENT_RESULT_VIEW_CHARS + 1

    if exact_ok and output_chars <= MAX_AGENT_RESULT_VIEW_CHARS:
        return REPRESENTATION_EXACT_OUTPUTS, dict(outputs_dict)

    if view is not None:
        return REPRESENTATION_AGENT_RESULT_VIEW, agent_result_view_to_wire(view)

    reason = REASON_INVALID_VIEW if view_omission is not None else REASON_MISSING_VIEW
    keys: list[str] = []
    omitted_key_count = 0
    candidates: list[str] = []
    for raw_key in outputs_dict.keys():
        if not isinstance(raw_key, str):
            omitted_key_count += 1
            continue
        key = raw_key.strip()
        if not key or len(key) > MAX_OUTPUT_KEY_CHARS:
            omitted_key_count += 1
            continue
        candidates.append(key)
    candidates.sort()
    keys = candidates[:MAX_DELIVERY_OUTPUT_KEYS]
    omitted_key_count += max(0, len(candidates) - len(keys))
    marker: dict[str, Any] = {
        "reason": reason,
        "observed_output_chars": int(output_chars),
        "maximum_content_chars": MAX_AGENT_RESULT_VIEW_CHARS,
        "output_keys": keys,
        "output_keys_omitted_count": omitted_key_count,
    }
    if view_omission is not None:
        marker["view_omission"] = agent_result_view_omission_to_wire(view_omission)
    return REPRESENTATION_UNAVAILABLE, marker


def select_result_representation_from_raw_pair(
    *,
    outputs: Mapping[str, Any] | dict[str, Any],
    agent_result_view: Any,
    agent_result_view_omitted: Any,
    exact_outputs_eligible: bool = True,
) -> tuple[str, dict[str, Any]]:
    view, view_omission = normalize_agent_result_view_pair(
        agent_result_view,
        agent_result_view_omitted,
    )
    return select_result_representation(
        outputs=outputs,
        view=view,
        view_omission=view_omission,
        exact_outputs_eligible=exact_outputs_eligible,
    )


def validate_stored_representation(
    kind: str,
    representation: Any,
) -> dict[str, Any] | None:
    """Strict stored-shape validator; rejects contradictory representation shapes."""
    if kind not in _ALLOWED_REPRESENTATION_KINDS:
        return None
    if not isinstance(representation, dict):
        return None
    if kind == REPRESENTATION_EXACT_OUTPUTS:
        if not is_json_safe(representation):
            return None
        try:
            if measure_compact_json_chars(representation) > MAX_AGENT_RESULT_VIEW_CHARS:
                return None
        except (TypeError, ValueError):
            return None
        return dict(representation)
    if kind == REPRESENTATION_AGENT_RESULT_VIEW:
        view, omitted = normalize_agent_result_view_pair(representation, None)
        if view is None or omitted is not None:
            return None
        return agent_result_view_to_wire(view)
    if kind == REPRESENTATION_UNAVAILABLE:
        if any(key not in _ALLOWED_UNAVAILABLE_KEYS for key in representation.keys()):
            return None
        reason = representation.get("reason")
        if reason == REASON_LANE_BUDGET:
            if set(representation.keys()) != {"reason"}:
                return None
            return {"reason": REASON_LANE_BUDGET}
        if reason not in {REASON_MISSING_VIEW, REASON_INVALID_VIEW}:
            return None
        observed = _strict_nonneg_int(representation.get("observed_output_chars"))
        maximum = _strict_nonneg_int(representation.get("maximum_content_chars"))
        omitted_keys = _strict_nonneg_int(representation.get("output_keys_omitted_count"))
        if observed is None or maximum is None or omitted_keys is None:
            return None
        if maximum != MAX_AGENT_RESULT_VIEW_CHARS:
            return None
        keys_raw = representation.get("output_keys")
        if not isinstance(keys_raw, list) or len(keys_raw) > MAX_DELIVERY_OUTPUT_KEYS:
            return None
        keys: list[str] = []
        for key in keys_raw:
            if not isinstance(key, str) or not key or key.strip() != key:
                return None
            if len(key) > MAX_OUTPUT_KEY_CHARS:
                return None
            keys.append(key)
        out: dict[str, Any] = {
            "reason": reason,
            "observed_output_chars": observed,
            "maximum_content_chars": maximum,
            "output_keys": keys,
            "output_keys_omitted_count": omitted_keys,
        }
        if "view_omission" in representation:
            if reason != REASON_INVALID_VIEW:
                return None
            omission = agent_result_view_omission_from_wire(representation.get("view_omission"))
            if omission is None:
                return None
            if omission.reason not in _ALLOWED_OMISSION_REASONS:
                return None
            out["view_omission"] = agent_result_view_omission_to_wire(omission)
        elif reason == REASON_INVALID_VIEW:
            return None
        return out
    return None


def project_representation_for_agent(
    *,
    kind: str,
    representation: Mapping[str, Any],
) -> dict[str, Any]:
    """Agent-facing projection: strip opaque continuity_key from provider views."""
    if kind == REPRESENTATION_AGENT_RESULT_VIEW:
        payload = representation.get("payload")
        return {
            "schema_version": representation.get("schema_version"),
            "schema_id": representation.get("schema_id"),
            "payload": dict(payload) if isinstance(payload, dict) else {},
        }
    return dict(representation)


def lane_budget_representation() -> dict[str, Any]:
    return {"reason": REASON_LANE_BUDGET}


def _strict_nonneg_int(value: Any) -> int | None:
    if type(value) is not int:
        return None
    if value < 0:
        return None
    return value


__all__ = [
    "MAX_AGENT_RESULT_VIEW_CHARS",
    "MAX_DELIVERY_OUTPUT_KEYS",
    "MAX_OUTPUT_KEY_CHARS",
    "REASON_INVALID_VIEW",
    "REASON_LANE_BUDGET",
    "REASON_MISSING_VIEW",
    "REPRESENTATION_AGENT_RESULT_VIEW",
    "REPRESENTATION_EXACT_OUTPUTS",
    "REPRESENTATION_UNAVAILABLE",
    "contains_host_or_binary_fields",
    "is_json_safe",
    "lane_budget_representation",
    "measure_compact_json_chars",
    "project_representation_for_agent",
    "select_result_representation",
    "select_result_representation_from_raw_pair",
    "validate_stored_representation",
]
