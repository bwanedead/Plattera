"""Host hydration delivery records (one-shot hydrate_next + pinned auto-hydration).

Stores and projects bounded ``result_representation`` envelopes using the shared
exact/view/unavailable policy. Retires prompt-visible raw ``hydrated_results``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.execution.contracts import ExecutionState
from harness.runtime.memory.host_hydration_errors import (
    MAX_ERROR_REASON_CODE_CHARS,
    omit_error_lane_details,
    project_hydration_error_lane,
    validate_optional_hydration_error_lane,
    validate_stored_hydration_error_lane,
)
from harness.runtime.memory.result_representation import (
    REASON_LANE_BUDGET,
    REPRESENTATION_AGENT_RESULT_VIEW,
    REPRESENTATION_EXACT_OUTPUTS,
    REPRESENTATION_UNAVAILABLE,
    contains_host_or_binary_fields,
    is_json_safe,
    lane_budget_representation,
    measure_compact_json_chars,
    project_representation_for_agent,
    select_result_representation_from_raw_pair,
    validate_stored_representation,
)

HOST_HYDRATION_DELIVERY_SCHEMA_VERSION = "host_hydration_delivery.v1"

# Combined prompt budget for one-shot + pinned hydration lanes (complete framing).
MAX_HOST_HYDRATION_PROMPT_CHARS = 24_000

MAX_HYDRATION_REF_CHARS = 256
MAX_HYDRATION_REFS = 32
MAX_HYDRATE_NEXT_REASON_CHARS = 400
MAX_SOURCE_TURN_INDEX = 1_000_000_000

_ONESHOT_ALLOWED_KEYS = frozenset(
    {
        "schema_version",
        "requested_refs",
        "resolved_refs",
        "reason",
        "errors",
        "errors_omitted_count",
        "status",
        "source_turn_index",
        "surfaced_iteration",
        "result_representation",
        "hydration_errors",
        "hydration_errors_omitted_count",
        # Legacy-only during decode; never re-emitted after canonicalize.
        "hydrated_results",
    }
)
_PINNED_ALLOWED_KEYS = frozenset(
    {
        "schema_version",
        "refs",
        "status",
        "surfaced_iteration",
        "result_representation",
        "hydration_errors",
        "hydration_errors_omitted_count",
        "hydrated_results",
    }
)
_RESULT_REPR_KEYS = frozenset({"representation_kind", "representation"})
_ALLOWED_STATUS = frozenset({"pending", "surfaced"})


def attach_hydration_result_representation(record: dict[str, Any], step_result: Any) -> None:
    """Attach bounded ``result_representation`` (+ sanitized errors) from a hydrate step."""
    record["schema_version"] = HOST_HYDRATION_DELIVERY_SCHEMA_VERSION
    record.pop("hydrated_results", None)

    execution_state = getattr(step_result, "execution_state", None)
    if execution_state != ExecutionState.EXECUTED:
        refusal = getattr(step_result, "refusal", None)
        raw_code = getattr(refusal, "reason_code", None) if refusal is not None else None
        if type(raw_code) is str and raw_code.strip() and raw_code.strip() == raw_code:
            code = raw_code if len(raw_code) <= MAX_ERROR_REASON_CODE_CHARS else "hydration_refused"
        else:
            code = "hydration_refused"
        errors, omitted = project_hydration_error_lane([{"reason_code": code}])
        record["hydration_errors"] = errors
        if omitted:
            record["hydration_errors_omitted_count"] = omitted
        record["result_representation"] = None
        return

    record_inner = getattr(step_result, "record", None)
    result = getattr(record_inner, "result", None) if record_inner is not None else None
    outputs_raw = getattr(result, "outputs", None) if result is not None else None
    outputs = dict(outputs_raw) if isinstance(outputs_raw, dict) else {}

    errors_payload = outputs.get("errors")
    if isinstance(errors_payload, list) and errors_payload:
        errors, omitted = project_hydration_error_lane(errors_payload)
        record["hydration_errors"] = errors
        if omitted:
            record["hydration_errors_omitted_count"] = omitted

    exact_eligible = not contains_host_or_binary_fields(outputs)
    kind, representation = select_result_representation_from_raw_pair(
        outputs=outputs,
        agent_result_view=getattr(result, "agent_result_view", None) if result is not None else None,
        agent_result_view_omitted=(
            getattr(result, "agent_result_view_omitted", None) if result is not None else None
        ),
        exact_outputs_eligible=exact_eligible,
    )
    record["result_representation"] = {
        "representation_kind": kind,
        "representation": representation,
    }


def canonicalize_legacy_hydrated_results(rows: Any) -> dict[str, Any] | None:
    """One-shot decode of legacy raw ``hydrated_results`` into a result_representation.

    Never re-emits the legacy shape. Oversized/unsafe rows without a provider view
    become ``unavailable``. Host/path/binary fields make exact ineligible.
    """
    from harness.execution.agent_result_view import MAX_AGENT_RESULT_VIEW_CHARS
    from harness.runtime.memory.result_representation import REASON_MISSING_VIEW

    if not isinstance(rows, (list, tuple)):
        return None
    results = list(rows)
    if not is_json_safe(results):
        return {
            "representation_kind": REPRESENTATION_UNAVAILABLE,
            "representation": {
                "reason": REASON_MISSING_VIEW,
                "observed_output_chars": MAX_AGENT_RESULT_VIEW_CHARS + 1,
                "maximum_content_chars": MAX_AGENT_RESULT_VIEW_CHARS,
                "output_keys": ["results"],
                "output_keys_omitted_count": 0,
            },
        }

    outputs = {"results": results}
    kind, representation = select_result_representation_from_raw_pair(
        outputs=outputs,
        agent_result_view=None,
        agent_result_view_omitted=None,
        exact_outputs_eligible=not contains_host_or_binary_fields(outputs),
    )
    return {"representation_kind": kind, "representation": representation}


def validate_host_hydration_result_representation(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        return None
    if any(key not in _RESULT_REPR_KEYS for key in raw.keys()):
        return None
    kind = raw.get("representation_kind")
    if not isinstance(kind, str):
        return None
    representation = validate_stored_representation(kind, raw.get("representation"))
    if representation is None:
        return None
    # Host hydration exact outputs must remain free of host/path/binary fields.
    if kind == REPRESENTATION_EXACT_OUTPUTS and contains_host_or_binary_fields(representation):
        return None
    return {"representation_kind": kind, "representation": representation}


def validate_stored_oneshot_hydration_record(row: Any) -> dict[str, Any] | None:
    """Strict resume validator for hydrate_next records; canonicalizes legacy once."""
    if row is None or not isinstance(row, Mapping):
        return None

    has_legacy = "hydrated_results" in row and row.get("hydrated_results") is not None
    schema = row.get("schema_version")
    if schema is not None and schema != HOST_HYDRATION_DELIVERY_SCHEMA_VERSION:
        return None
    if any(key not in _ONESHOT_ALLOWED_KEYS for key in row.keys()):
        return None
    if schema == HOST_HYDRATION_DELIVERY_SCHEMA_VERSION and has_legacy:
        return None

    source_turn_index = _strict_bounded_index(row.get("source_turn_index"), MAX_SOURCE_TURN_INDEX)
    if source_turn_index is None:
        return None

    requested_refs = _validate_ref_list(row.get("requested_refs"))
    resolved_refs = _validate_ref_list(row.get("resolved_refs"))
    if requested_refs is None or resolved_refs is None:
        return None

    reason = row.get("reason")
    if reason is not None:
        if type(reason) is not str or reason.strip() != reason:
            return None
        if len(reason) > MAX_HYDRATE_NEXT_REASON_CHARS:
            return None

    errors_raw = row.get("errors")
    if errors_raw is None:
        errors: list[dict[str, Any]] = []
    else:
        validated_errors = validate_stored_hydration_error_lane(errors_raw)
        if validated_errors is None:
            return None
        errors = validated_errors

    errors_omitted = row.get("errors_omitted_count")
    if errors_omitted is not None:
        errors_omitted = _strict_positive_int(errors_omitted)
        if errors_omitted is None:
            return None

    hydration_errors = validate_optional_hydration_error_lane(row.get("hydration_errors"))
    if hydration_errors is False:
        return None

    hydration_errors_omitted = row.get("hydration_errors_omitted_count")
    if hydration_errors_omitted is not None:
        hydration_errors_omitted = _strict_positive_int(hydration_errors_omitted)
        if hydration_errors_omitted is None:
            return None

    status = row.get("status")
    if not isinstance(status, str) or status not in _ALLOWED_STATUS:
        return None

    surfaced_iteration = row.get("surfaced_iteration")
    if surfaced_iteration is not None:
        surfaced_iteration = _strict_bounded_index(surfaced_iteration, MAX_SOURCE_TURN_INDEX)
        if surfaced_iteration is None:
            return None

    result_representation: dict[str, Any] | None
    if has_legacy:
        result_representation = canonicalize_legacy_hydrated_results(row.get("hydrated_results"))
        if result_representation is None:
            return None
        validated_rr = validate_host_hydration_result_representation(result_representation)
        if validated_rr is None:
            return None
        result_representation = validated_rr
    elif "result_representation" in row:
        rr_raw = row.get("result_representation")
        if rr_raw is None:
            result_representation = None
        else:
            result_representation = validate_host_hydration_result_representation(rr_raw)
            if result_representation is None:
                return None
    else:
        result_representation = None

    if status == "pending":
        if surfaced_iteration is not None:
            return None
        if result_representation is not None:
            return None
        if hydration_errors is not None:
            return None
        if hydration_errors_omitted is not None:
            return None
        if has_legacy:
            return None
    else:  # surfaced
        if surfaced_iteration is None:
            return None
        has_outcome = (
            result_representation is not None
            or bool(errors)
            or errors_omitted is not None
            or (isinstance(hydration_errors, list) and bool(hydration_errors))
            or hydration_errors_omitted is not None
        )
        if not has_outcome:
            return None

    out: dict[str, Any] = {
        "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
        "source_turn_index": source_turn_index,
        "requested_refs": requested_refs,
        "resolved_refs": resolved_refs,
        "reason": reason if reason else None,
        "errors": errors,
        "result_representation": result_representation,
        "hydration_errors": hydration_errors,
        "status": status,
        "surfaced_iteration": surfaced_iteration,
    }
    if errors_omitted is not None:
        out["errors_omitted_count"] = errors_omitted
    if hydration_errors_omitted is not None:
        out["hydration_errors_omitted_count"] = hydration_errors_omitted
    return out


def validate_stored_pinned_hydration_record(row: Any) -> dict[str, Any] | None:
    """Strict resume validator for pinned-ref auto-hydration records."""
    if row is None or not isinstance(row, Mapping):
        return None

    has_legacy = "hydrated_results" in row and row.get("hydrated_results") is not None
    schema = row.get("schema_version")
    if schema is not None and schema != HOST_HYDRATION_DELIVERY_SCHEMA_VERSION:
        return None
    if any(key not in _PINNED_ALLOWED_KEYS for key in row.keys()):
        return None
    if schema == HOST_HYDRATION_DELIVERY_SCHEMA_VERSION and has_legacy:
        return None

    refs = _validate_ref_list(row.get("refs"))
    if refs is None:
        return None

    status = row.get("status")
    # Pinned hydration is produced only as surfaced; reject invented pending rows.
    if status != "surfaced":
        return None

    surfaced_iteration = row.get("surfaced_iteration")
    surfaced_iteration = _strict_bounded_index(surfaced_iteration, MAX_SOURCE_TURN_INDEX)
    if surfaced_iteration is None:
        return None

    hydration_errors = validate_optional_hydration_error_lane(row.get("hydration_errors"))
    if hydration_errors is False:
        return None
    hydration_errors_omitted = row.get("hydration_errors_omitted_count")
    if hydration_errors_omitted is not None:
        hydration_errors_omitted = _strict_positive_int(hydration_errors_omitted)
        if hydration_errors_omitted is None:
            return None

    if has_legacy:
        result_representation = canonicalize_legacy_hydrated_results(row.get("hydrated_results"))
        if result_representation is None:
            return None
        validated_rr = validate_host_hydration_result_representation(result_representation)
        if validated_rr is None:
            return None
        result_representation = validated_rr
    elif "result_representation" in row:
        rr_raw = row.get("result_representation")
        if rr_raw is None:
            result_representation = None
        else:
            result_representation = validate_host_hydration_result_representation(rr_raw)
            if result_representation is None:
                return None
    else:
        result_representation = None

    has_outcome = (
        result_representation is not None
        or (isinstance(hydration_errors, list) and bool(hydration_errors))
        or hydration_errors_omitted is not None
    )
    if not has_outcome:
        return None

    out: dict[str, Any] = {
        "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
        "refs": refs,
        "status": status,
        "surfaced_iteration": surfaced_iteration,
        "result_representation": result_representation,
        "hydration_errors": hydration_errors if hydration_errors is not None else [],
    }
    if hydration_errors_omitted is not None:
        out["hydration_errors_omitted_count"] = hydration_errors_omitted
    return out


def project_oneshot_hydration_for_prompt(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    out: dict[str, Any] = {
        "source_turn_index": int(record.get("source_turn_index") or 0),
        "requested_refs": list(record.get("requested_refs") or []),
        "resolved_refs": list(record.get("resolved_refs") or []),
    }
    reason = record.get("reason")
    if isinstance(reason, str) and reason:
        out["reason"] = reason
    errors, errors_omitted = project_hydration_error_lane(record.get("errors") or [])
    stored_omitted = record.get("errors_omitted_count")
    if type(stored_omitted) is int and stored_omitted > 0:
        errors_omitted += stored_omitted
    if errors:
        out["errors"] = errors
    if errors_omitted:
        out["errors_omitted_count"] = errors_omitted
    _attach_projected_hydration_errors(record, out)
    rr = _project_result_representation_block(record.get("result_representation"))
    if rr is not None:
        out["result_representation"] = rr
    return out


def project_pinned_hydration_for_prompt(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    out: dict[str, Any] = {
        "refs": list(record.get("refs") or []),
        "status": str(record.get("status") or ""),
    }
    _attach_projected_hydration_errors(record, out)
    rr = _project_result_representation_block(record.get("result_representation"))
    if rr is not None:
        out["result_representation"] = rr
    return out


def _attach_projected_hydration_errors(record: Mapping[str, Any], out: dict[str, Any]) -> None:
    """Project hydration_errors + omitted count; preserve count when rows are empty."""
    hydration_errors_raw = record.get("hydration_errors")
    stored_hyd_omitted = record.get("hydration_errors_omitted_count")
    has_rows = isinstance(hydration_errors_raw, list) and bool(hydration_errors_raw)
    has_stored_omission = type(stored_hyd_omitted) is int and stored_hyd_omitted > 0
    if not has_rows and not has_stored_omission:
        return
    rows_input: list[Any] = (
        list(hydration_errors_raw) if isinstance(hydration_errors_raw, list) else []
    )
    hydration_errors, hyd_omitted = project_hydration_error_lane(rows_input)
    if has_stored_omission:
        hyd_omitted += stored_hyd_omitted
    if hydration_errors:
        out["hydration_errors"] = hydration_errors
    if hyd_omitted:
        out["hydration_errors_omitted_count"] = hyd_omitted
    # Do not invent placeholder rows when every source error was omitted.


def measure_framed_hydration_prompt_chars(
    oneshot: dict[str, Any] | None,
    pinned: dict[str, Any] | None,
) -> int:
    """Measure the complete structured-state hydration fragment including lane keys."""
    fragment: dict[str, Any] = {}
    if oneshot is not None:
        fragment["agent_requested_hydration"] = oneshot
    if pinned is not None:
        fragment["pinned_refs_hydration"] = pinned
    if not fragment:
        return 0
    return measure_compact_json_chars(fragment)


def apply_combined_hydration_lane_budget(
    *,
    oneshot: dict[str, Any] | None,
    pinned: dict[str, Any] | None,
    max_chars: int = MAX_HOST_HYDRATION_PROMPT_CHARS,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Prefer one-shot content under pressure; never return an over-budget framed fragment.

    Reduction order (one-shot priority):
    1. Full lanes
    2. Suppress pinned representation
    3. Remove pinned error detail
    4. Remove one-shot error detail (retain stable codes/counts)
    5. Drop pinned lane entirely
    6. Suppress one-shot representation
    7. Identity-only one-shot, then None only for a pathologically tiny bound
    """
    if oneshot is None and pinned is None:
        return None, None

    oneshot_out = dict(oneshot) if oneshot is not None else None
    pinned_out = dict(pinned) if pinned is not None else None

    if measure_framed_hydration_prompt_chars(oneshot_out, pinned_out) <= max_chars:
        return oneshot_out, pinned_out

    # 2. Suppress pinned representation.
    pinned_out = _with_lane_budget_representation(pinned_out)
    if measure_framed_hydration_prompt_chars(oneshot_out, pinned_out) <= max_chars:
        return oneshot_out, pinned_out

    # 3. Remove pinned error detail.
    if pinned_out is not None:
        pinned_out = omit_error_lane_details(
            pinned_out,
            errors_key="hydration_errors",
            omitted_count_key="hydration_errors_omitted_count",
        )
    if measure_framed_hydration_prompt_chars(oneshot_out, pinned_out) <= max_chars:
        return oneshot_out, pinned_out

    # 4. Remove one-shot error detail while retaining stable codes/counts.
    if oneshot_out is not None:
        oneshot_out = omit_error_lane_details(
            oneshot_out, errors_key="errors", omitted_count_key="errors_omitted_count"
        )
        oneshot_out = omit_error_lane_details(
            oneshot_out,
            errors_key="hydration_errors",
            omitted_count_key="hydration_errors_omitted_count",
        )
        if "reason" in oneshot_out:
            oneshot_out = dict(oneshot_out)
            oneshot_out.pop("reason", None)
    if measure_framed_hydration_prompt_chars(oneshot_out, pinned_out) <= max_chars:
        return oneshot_out, pinned_out

    # 5. Drop the pinned lane entirely.
    pinned_out = None
    if measure_framed_hydration_prompt_chars(oneshot_out, pinned_out) <= max_chars:
        return oneshot_out, pinned_out

    # 6. Only then suppress the one-shot representation.
    oneshot_out = _with_lane_budget_representation(oneshot_out)
    if measure_framed_hydration_prompt_chars(oneshot_out, pinned_out) <= max_chars:
        return oneshot_out, pinned_out

    # 7. Identity-only one-shot, then None for pathological tiny bounds.
    if oneshot_out is not None:
        oneshot_out = _identity_only_oneshot(oneshot_out)
    if measure_framed_hydration_prompt_chars(oneshot_out, pinned_out) <= max_chars:
        return oneshot_out, pinned_out

    return None, None


def project_hydration_representation_for_audit(
    result_representation: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Compact audit summary — never copies full hydration payloads."""
    if not isinstance(result_representation, Mapping):
        return None
    kind = result_representation.get("representation_kind")
    if not isinstance(kind, str):
        return None
    representation = result_representation.get("representation")
    if not isinstance(representation, Mapping):
        return None
    out: dict[str, Any] = {"representation_kind": kind}
    if kind == REPRESENTATION_AGENT_RESULT_VIEW:
        schema_id = representation.get("schema_id")
        if isinstance(schema_id, str) and schema_id:
            out["schema_id"] = schema_id[:256]
    elif kind == REPRESENTATION_EXACT_OUTPUTS:
        keys = sorted(k for k in representation.keys() if isinstance(k, str))
        out["exact_output_keys"] = keys[:32]
        results = representation.get("results")
        if isinstance(results, list):
            out["result_count"] = len(results)
    elif kind == REPRESENTATION_UNAVAILABLE:
        reason = representation.get("reason")
        if isinstance(reason, str) and reason:
            out["unavailable_reason"] = reason[:128]
    return out


def _project_result_representation_block(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    kind = raw.get("representation_kind")
    representation = raw.get("representation")
    if not isinstance(kind, str) or not isinstance(representation, Mapping):
        return None
    return {
        "representation_kind": kind,
        "representation": project_representation_for_agent(
            kind=kind,
            representation=representation,
        ),
    }


def _with_lane_budget_representation(lane: dict[str, Any] | None) -> dict[str, Any] | None:
    if lane is None:
        return None
    out = dict(lane)
    prior = out.get("result_representation")
    if isinstance(prior, Mapping) and prior.get("representation_kind") == REPRESENTATION_UNAVAILABLE:
        prior_repr = prior.get("representation")
        if isinstance(prior_repr, Mapping) and prior_repr.get("reason") == REASON_LANE_BUDGET:
            return out
    if "result_representation" in out and out.get("result_representation") is not None:
        out["result_representation"] = {
            "representation_kind": REPRESENTATION_UNAVAILABLE,
            "representation": lane_budget_representation(),
        }
    return out


def _identity_only_oneshot(lane: dict[str, Any]) -> dict[str, Any]:
    requested = [r for r in list(lane.get("requested_refs") or []) if isinstance(r, str)]
    resolved = [r for r in list(lane.get("resolved_refs") or []) if isinstance(r, str)]
    out: dict[str, Any] = {
        "source_turn_index": int(lane.get("source_turn_index") or 0),
        "requested_refs": [],
        "resolved_refs": [],
        "requested_refs_omitted_count": len(requested),
        "resolved_refs_omitted_count": len(resolved),
        "result_representation": {
            "representation_kind": REPRESENTATION_UNAVAILABLE,
            "representation": lane_budget_representation(),
        },
    }
    # Preserve compact stable reason codes from prior error omission if present.
    for key in ("errors_reason_codes", "hydration_errors_reason_codes"):
        codes = lane.get(key)
        if isinstance(codes, list) and codes:
            out[key] = [str(c) for c in codes[:16] if isinstance(c, str)]
    for key in ("errors_omitted_count", "hydration_errors_omitted_count"):
        value = lane.get(key)
        if type(value) is int and value > 0:
            out[key] = value
    return out


def _validate_ref_list(raw: Any) -> list[str] | None:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        return None
    if len(raw) > MAX_HYDRATION_REFS:
        return None
    out: list[str] = []
    for item in raw:
        if type(item) is not str:
            return None
        if not item or item.strip() != item:
            return None
        if len(item) > MAX_HYDRATION_REF_CHARS:
            return None
        out.append(item)
    return out


def _strict_bounded_index(value: Any, maximum: int) -> int | None:
    if type(value) is not int:
        return None
    if value < 0 or value > maximum:
        return None
    return value


def _strict_positive_int(value: Any) -> int | None:
    if type(value) is not int:
        return None
    if value <= 0:
        return None
    return value


__all__ = [
    "HOST_HYDRATION_DELIVERY_SCHEMA_VERSION",
    "MAX_HOST_HYDRATION_PROMPT_CHARS",
    "apply_combined_hydration_lane_budget",
    "attach_hydration_result_representation",
    "canonicalize_legacy_hydrated_results",
    "measure_framed_hydration_prompt_chars",
    "project_hydration_representation_for_audit",
    "project_oneshot_hydration_for_prompt",
    "project_pinned_hydration_for_prompt",
    "validate_host_hydration_result_representation",
    "validate_stored_oneshot_hydration_record",
    "validate_stored_pinned_hydration_record",
]
