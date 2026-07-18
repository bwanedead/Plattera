"""Generic agent-result-view envelope: validate and transport only.

Domain/tool providers author coherent agent-facing views. This module owns the
mechanical envelope, bounds, and codec. It does not interpret schema IDs,
continuity keys, or payload fields, and it does not project into prompts.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

AGENT_RESULT_VIEW_SCHEMA_VERSION = "agent_result_view.v1"
MAX_AGENT_RESULT_VIEW_CHARS = 12_000
MAX_SCHEMA_ID_CHARS = 256
MAX_CONTINUITY_KEY_CHARS = 256

OMISSION_REASON_INVALID_SHAPE = "invalid_shape"
OMISSION_REASON_UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
OMISSION_REASON_NOT_JSON_SAFE = "not_json_safe"
OMISSION_REASON_VIEW_BUDGET = "view_budget"

_ALLOWED_OMISSION_REASONS = frozenset(
    {
        OMISSION_REASON_INVALID_SHAPE,
        OMISSION_REASON_UNSUPPORTED_SCHEMA_VERSION,
        OMISSION_REASON_NOT_JSON_SAFE,
        OMISSION_REASON_VIEW_BUDGET,
    }
)
_ALLOWED_ENVELOPE_KEYS = frozenset({"schema_version", "schema_id", "payload", "continuity_key"})
_ALLOWED_OMISSION_KEYS = frozenset({"reason", "observed_chars", "maximum_chars"})


@dataclass(frozen=True)
class AgentResultView:
    schema_version: str
    schema_id: str
    payload: dict[str, Any]
    continuity_key: str | None = None


@dataclass(frozen=True)
class AgentResultViewOmission:
    reason: str
    observed_chars: int | None = None
    maximum_chars: int | None = None


def agent_result_view_to_wire(view: AgentResultView) -> dict[str, Any]:
    wire: dict[str, Any] = {
        "schema_version": view.schema_version,
        "schema_id": view.schema_id,
        "payload": dict(view.payload),
    }
    if view.continuity_key is not None:
        wire["continuity_key"] = view.continuity_key
    return wire


def agent_result_view_omission_to_wire(omission: AgentResultViewOmission) -> dict[str, Any]:
    wire: dict[str, Any] = {"reason": omission.reason}
    if omission.observed_chars is not None:
        wire["observed_chars"] = omission.observed_chars
    if omission.maximum_chars is not None:
        wire["maximum_chars"] = omission.maximum_chars
    return wire


def agent_result_view_omission_from_wire(raw: object) -> AgentResultViewOmission | None:
    if not isinstance(raw, Mapping):
        return None
    if any(key not in _ALLOWED_OMISSION_KEYS for key in raw.keys()):
        return None
    reason = str(raw.get("reason") or "").strip()
    if reason not in _ALLOWED_OMISSION_REASONS:
        return None
    observed = raw.get("observed_chars")
    maximum = raw.get("maximum_chars")
    if "observed_chars" in raw and observed is not None and not (
        isinstance(observed, int) and not isinstance(observed, bool)
    ):
        return None
    if "maximum_chars" in raw and maximum is not None and not (
        isinstance(maximum, int) and not isinstance(maximum, bool)
    ):
        return None
    return AgentResultViewOmission(
        reason=reason,
        observed_chars=int(observed) if isinstance(observed, int) and not isinstance(observed, bool) else None,
        maximum_chars=int(maximum) if isinstance(maximum, int) and not isinstance(maximum, bool) else None,
    )


def measure_agent_result_view_chars(wire_envelope: Mapping[str, Any]) -> int:
    """Return compact JSON character length of the complete wire envelope."""
    return len(
        json.dumps(
            dict(wire_envelope),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def build_agent_result_view(
    *,
    schema_id: str,
    payload: Mapping[str, Any],
    continuity_key: str | None = None,
    schema_version: str = AGENT_RESULT_VIEW_SCHEMA_VERSION,
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    """Public builder/normalizer for domain providers.

    Malformed builder inputs return an omission marker rather than raising.
    """
    try:
        payload_dict = dict(payload)
    except (TypeError, ValueError):
        return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)
    candidate: dict[str, Any] = {
        "schema_version": schema_version,
        "schema_id": schema_id,
        "payload": payload_dict,
    }
    if continuity_key is not None:
        candidate["continuity_key"] = continuity_key
    return parse_agent_result_view(candidate)


def normalize_agent_result_view_pair(
    view: object | None = None,
    omission: object | None = None,
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    """Canonical mutual-exclusivity normalizer for view/omission pairs.

    - Valid view only → retain view.
    - Valid omission only → retain omission.
    - Both supplied → omit view and emit ``invalid_shape``.
    - Invalid view → explicit omission.
    - Malformed omission-only input → ``invalid_shape`` omission.
    - Neither → ``(None, None)``.
    """
    has_view = view is not None
    has_omission = omission is not None
    if has_view and has_omission:
        return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)
    if has_view:
        if isinstance(view, AgentResultView):
            return parse_agent_result_view(agent_result_view_to_wire(view))
        return parse_agent_result_view(view)
    if has_omission:
        if isinstance(omission, AgentResultViewOmission):
            restored = agent_result_view_omission_from_wire(agent_result_view_omission_to_wire(omission))
        else:
            restored = agent_result_view_omission_from_wire(omission)
        if restored is None:
            return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)
        return None, restored
    return None, None


def parse_agent_result_view(
    raw: object,
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    """Canonical validator/codec.

    Absent/None stays absent (no omission). A supplied but invalid envelope is
    omitted wholesale with an explicit mechanical reason.
    """
    if raw is None:
        return None, None
    if not isinstance(raw, Mapping):
        return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)
    if any(key not in _ALLOWED_ENVELOPE_KEYS for key in raw.keys()):
        return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)

    schema_version = raw.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)
    if schema_version.strip() != AGENT_RESULT_VIEW_SCHEMA_VERSION:
        return None, AgentResultViewOmission(reason=OMISSION_REASON_UNSUPPORTED_SCHEMA_VERSION)

    schema_id_raw = raw.get("schema_id")
    if not isinstance(schema_id_raw, str):
        return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)
    schema_id = schema_id_raw.strip()
    if not schema_id or len(schema_id) > MAX_SCHEMA_ID_CHARS:
        return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)

    payload_raw = raw.get("payload")
    if not isinstance(payload_raw, dict):
        return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)
    if any(not isinstance(key, str) for key in payload_raw.keys()):
        return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)

    continuity_key: str | None = None
    if "continuity_key" in raw and raw.get("continuity_key") is not None:
        continuity_raw = raw.get("continuity_key")
        if not isinstance(continuity_raw, str):
            return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)
        continuity_key = continuity_raw.strip()
        if not continuity_key or len(continuity_key) > MAX_CONTINUITY_KEY_CHARS:
            return None, AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)

    if not _is_json_safe(payload_raw):
        return None, AgentResultViewOmission(reason=OMISSION_REASON_NOT_JSON_SAFE)

    view = AgentResultView(
        schema_version=AGENT_RESULT_VIEW_SCHEMA_VERSION,
        schema_id=schema_id,
        payload=dict(payload_raw),
        continuity_key=continuity_key,
    )
    wire = agent_result_view_to_wire(view)
    try:
        observed = measure_agent_result_view_chars(wire)
    except (TypeError, ValueError):
        return None, AgentResultViewOmission(reason=OMISSION_REASON_NOT_JSON_SAFE)

    if observed > MAX_AGENT_RESULT_VIEW_CHARS:
        return None, AgentResultViewOmission(
            reason=OMISSION_REASON_VIEW_BUDGET,
            observed_chars=observed,
            maximum_chars=MAX_AGENT_RESULT_VIEW_CHARS,
        )
    return view, None


def _is_json_safe(value: Any) -> bool:
    """Accept JSON-native values only (lists, not tuples)."""
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_json_safe(v) for k, v in value.items())
    if isinstance(value, list):
        return all(_is_json_safe(item) for item in value)
    return False
