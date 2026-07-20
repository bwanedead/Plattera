"""Deed-to-IR AgentResultView for canonical ``hydrate_artifact_refs`` results.

Owns a keyless, request-aware projection that preserves operand-to-evidence
associations from tooling's compact operand projector. Does not diagnose source
errors, select evidence, or alter raw image transport.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from harness.execution.agent_result_view import (
    OMISSION_REASON_INVALID_SHAPE,
    OMISSION_REASON_NOT_JSON_SAFE,
    AgentResultViewOmission,
)
from tooling.mapping.deed_to_ir.mapping_operands_projection import (
    compact_mapping_operands_for_projection,
)

from .result_view_common import (
    MAX_ERROR_MESSAGE_CHARS,
    bound_text,
    json_native,
    payload_fits,
    strict_string_list,
    strip_host_value,
    try_build_view,
)

SCHEMA_HYDRATE_ARTIFACT_REFS = "deed_to_ir.hydrate_artifact_refs.v1"

MAX_HYDRATE_RESULT_ROWS = 32
MAX_HYDRATE_OMISSION_ROWS = 32
MAX_HYDRATE_ERROR_ROWS = 16
MAX_ERROR_CODE_CHARS = 128
MAX_ERROR_REF_ID_CHARS = 256

_OPERAND_SUITE_TYPE = "deed_to_ir_operand_suite"
_IMAGE_KINDS = frozenset({"upstream_source_image", "upstream_derived_image"})
_IMAGE_META_KEYS = (
    "ref_id",
    "kind",
    "artifact_type",
    "role",
    "basename",
    "width_height",
    "parent_ref_id",
    "parent_ref",
    "exists",
    "size_bytes",
    "media_type",
    "sidecar_name",
    "sub_action",
)


def build_hydrate_artifact_refs_view(
    outputs: Mapping[str, Any],
    *,
    action_inputs: Mapping[str, Any] | None = None,
):
    """Keyless hydrate view: operand suites first, then other complete rows."""
    source_results, results_error = _require_list_collection(outputs, key="results")
    if results_error is not None:
        return None, results_error
    source_errors, errors_error = _require_list_collection(outputs, key="errors")
    if errors_error is not None:
        return None, errors_error

    inputs = action_inputs if isinstance(action_inputs, Mapping) else None
    source_count = len(source_results)

    mapping_rows: list[Mapping[str, Any]] = []
    omitted_extra = 0
    for item in source_results:
        if isinstance(item, Mapping):
            mapping_rows.append(item)
        else:
            # Non-mapping elements are invalid intake omissions (no descriptor).
            omitted_extra += 1

    ordered = _order_results_by_request(
        mapping_rows,
        strict_string_list(inputs.get("ref_ids") if inputs else None),
    )

    operand_candidates: list[dict[str, Any]] = []
    other_candidates: list[tuple[Mapping[str, Any], dict[str, Any] | None, str]] = []
    for raw in ordered:
        if _is_operand_suite(raw):
            projected, reason = _project_operand_suite_row(raw)
            if projected is None:
                other_candidates.append(
                    (raw, None, reason or OMISSION_REASON_INVALID_SHAPE)
                )
            else:
                operand_candidates.append(projected)
            continue
        projected, reason = _sanitize_other_result_row(raw)
        if projected is None:
            other_candidates.append(
                (raw, None, reason or OMISSION_REASON_INVALID_SHAPE)
            )
        else:
            other_candidates.append((raw, projected, "ok"))

    kept: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []

    # Fit priority: identity (via payload) → operand suites → other rows.
    for row in operand_candidates[:MAX_HYDRATE_RESULT_ROWS]:
        if _try_results(
            outputs,
            source_count=source_count,
            kept=kept + [row],
            omitted=omitted,
            omitted_extra=omitted_extra,
        ):
            kept.append(row)
            continue
        omitted_extra = _record_omission(
            outputs,
            source_count=source_count,
            kept=kept,
            omitted=omitted,
            omitted_extra=omitted_extra,
            source_row=row,
            reason="view_budget",
        )

    omitted_extra += max(0, len(operand_candidates) - MAX_HYDRATE_RESULT_ROWS)

    remaining_slots = max(0, MAX_HYDRATE_RESULT_ROWS - len(kept))
    other_projected = [
        (raw, projected)
        for raw, projected, status in other_candidates
        if status == "ok" and projected is not None
    ]
    other_invalid = [
        (raw, status)
        for raw, projected, status in other_candidates
        if status != "ok"
    ]

    for raw, projected in other_projected[:remaining_slots]:
        assert projected is not None
        if _try_results(
            outputs,
            source_count=source_count,
            kept=kept + [projected],
            omitted=omitted,
            omitted_extra=omitted_extra,
        ):
            kept.append(projected)
            continue
        omitted_extra = _record_omission(
            outputs,
            source_count=source_count,
            kept=kept,
            omitted=omitted,
            omitted_extra=omitted_extra,
            source_row=raw,
            reason="view_budget",
        )

    omitted_extra += max(0, len(other_projected) - remaining_slots)

    for raw, status in other_invalid:
        omitted_extra = _record_omission(
            outputs,
            source_count=source_count,
            kept=kept,
            omitted=omitted,
            omitted_extra=omitted_extra,
            source_row=raw,
            reason=status,
        )

    results_omitted_count = len(omitted) + max(0, omitted_extra)
    # Honest accounting: every source element is kept or omitted.
    assert len(kept) + results_omitted_count == source_count

    error_candidates: list[dict[str, Any]] = []
    errors_intake_omitted = 0
    for item in source_errors:
        sanitized = _sanitize_error_row(item)
        if sanitized is None:
            errors_intake_omitted += 1
        else:
            error_candidates.append(sanitized)

    errors_kept, errors_fit_omitted = _fit_error_rows(
        outputs,
        source_count=source_count,
        results=kept,
        results_omitted=omitted,
        results_omitted_extra=omitted_extra,
        error_rows=error_candidates,
    )
    errors_omitted_count = errors_intake_omitted + errors_fit_omitted
    assert len(errors_kept) + errors_omitted_count == len(source_errors)

    payload = _hydrate_payload(
        outputs,
        source_count=source_count,
        results=kept,
        results_omitted=omitted,
        results_omitted_extra=omitted_extra,
        errors=errors_kept,
        errors_omitted_count=errors_omitted_count,
    )
    return try_build_view(
        schema_id=SCHEMA_HYDRATE_ARTIFACT_REFS,
        payload=payload,
        continuity_key=None,
    )


def _require_list_collection(
    outputs: Mapping[str, Any],
    *,
    key: str,
) -> tuple[list[Any], AgentResultViewOmission | None]:
    """Missing key → empty list; present value must be a list (null is invalid)."""
    if key not in outputs:
        return [], None
    raw = outputs.get(key)
    if not isinstance(raw, list):
        return [], AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE)
    return list(raw), None


def _is_json_safe(value: Any) -> bool:
    """Accept JSON-native values only (lists, not tuples). Matches harness codec."""
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_json_safe(v) for k, v in value.items())
    if isinstance(value, list):
        return all(_is_json_safe(item) for item in value)
    return False


def _is_operand_suite(raw: Mapping[str, Any]) -> bool:
    artifact_type = raw.get("artifact_type")
    return isinstance(artifact_type, str) and artifact_type == _OPERAND_SUITE_TYPE


def _project_operand_suite_row(
    raw: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    ref_id = raw.get("ref_id")
    if not isinstance(ref_id, str) or not ref_id.strip():
        return None, OMISSION_REASON_INVALID_SHAPE
    compact = compact_mapping_operands_for_projection(dict(raw))
    if not isinstance(compact, Mapping):
        compact = {
            key: raw[key]
            for key in ("operand_suite_ref", "projection_mode", "totals", "truncation")
            if key in raw and raw[key] is not None
        }
    cleaned = json_native(strip_host_value(dict(compact)))
    if not isinstance(cleaned, Mapping):
        return None, OMISSION_REASON_INVALID_SHAPE
    row: dict[str, Any] = {
        "ref_id": ref_id.strip(),
        "artifact_type": _OPERAND_SUITE_TYPE,
    }
    for key, value in cleaned.items():
        if key in {"ref_id", "artifact_type"}:
            continue
        if value is not None:
            row[str(key)] = value
    if not _is_json_safe(row):
        return None, OMISSION_REASON_NOT_JSON_SAFE
    return row, None


def _sanitize_other_result_row(
    raw: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    ref_id = raw.get("ref_id")
    if not isinstance(ref_id, str) or not ref_id.strip():
        return None, OMISSION_REASON_INVALID_SHAPE

    kind = raw.get("kind")
    artifact_type = raw.get("artifact_type")
    kind_text = kind.strip() if isinstance(kind, str) and kind.strip() else None
    type_text = (
        artifact_type.strip()
        if isinstance(artifact_type, str) and artifact_type.strip()
        else None
    )
    if kind_text is None and type_text is None:
        return None, OMISSION_REASON_INVALID_SHAPE

    if kind_text in _IMAGE_KINDS or (
        type_text == "mapping_sidecar"
        and str(raw.get("media_type") or "").startswith("image/")
    ):
        row: dict[str, Any] = {"ref_id": ref_id.strip()}
        for key in _IMAGE_META_KEYS:
            if key == "ref_id":
                continue
            value = raw.get(key)
            if value in (None, "", [], (), {}):
                continue
            row[key] = json_native(value)
        if not _is_json_safe(row):
            return None, OMISSION_REASON_NOT_JSON_SAFE
        return row, None

    cleaned = json_native(strip_host_value(dict(raw)))
    if not isinstance(cleaned, Mapping):
        return None, OMISSION_REASON_INVALID_SHAPE
    out = dict(cleaned)
    out["ref_id"] = ref_id.strip()
    if not _is_json_safe(out):
        return None, OMISSION_REASON_NOT_JSON_SAFE
    return out, None


def _order_results_by_request(
    results: Sequence[Mapping[str, Any]],
    ref_ids: Sequence[str],
) -> list[Mapping[str, Any]]:
    if not ref_ids:
        return list(results)
    remaining = list(results)
    ordered: list[Mapping[str, Any]] = []
    for rid in ref_ids:
        still: list[Mapping[str, Any]] = []
        for row in remaining:
            row_ref = row.get("ref_id")
            if isinstance(row_ref, str) and row_ref.strip() == rid:
                ordered.append(row)
            else:
                still.append(row)
        remaining = still
    ordered.extend(remaining)
    return ordered


def _try_results(
    outputs: Mapping[str, Any],
    *,
    source_count: int,
    kept: Sequence[Mapping[str, Any]],
    omitted: Sequence[Mapping[str, Any]],
    omitted_extra: int,
) -> bool:
    payload = _hydrate_payload(
        outputs,
        source_count=source_count,
        results=kept,
        results_omitted=omitted,
        results_omitted_extra=omitted_extra,
        errors=[],
        errors_omitted_count=0,
    )
    return payload_fits(
        schema_id=SCHEMA_HYDRATE_ARTIFACT_REFS,
        payload=payload,
        continuity_key=None,
    )


def _record_omission(
    outputs: Mapping[str, Any],
    *,
    source_count: int,
    kept: list[dict[str, Any]],
    omitted: list[dict[str, Any]],
    omitted_extra: int,
    source_row: Mapping[str, Any],
    reason: str,
) -> int:
    desc = _omission_descriptor(source_row, reason=reason)
    if desc is None:
        return omitted_extra + 1
    if len(omitted) >= MAX_HYDRATE_OMISSION_ROWS:
        return omitted_extra + 1
    trial = omitted + [desc]
    if _try_results(
        outputs,
        source_count=source_count,
        kept=kept,
        omitted=trial,
        omitted_extra=omitted_extra,
    ):
        omitted.append(desc)
        return omitted_extra
    return omitted_extra + 1


def _omission_descriptor(
    row: Mapping[str, Any],
    *,
    reason: str,
) -> dict[str, Any] | None:
    ref_id = row.get("ref_id")
    if not isinstance(ref_id, str) or not ref_id.strip():
        return None
    desc: dict[str, Any] = {"ref_id": ref_id.strip(), "reason": reason}
    artifact_type = row.get("artifact_type")
    if isinstance(artifact_type, str) and artifact_type.strip():
        desc["artifact_type"] = artifact_type.strip()
    kind = row.get("kind")
    if isinstance(kind, str) and kind.strip():
        desc["kind"] = kind.strip()
    return desc


def _canonical_hydrated_count(
    outputs: Mapping[str, Any],
    *,
    source_count: int,
) -> int:
    value = outputs.get("hydrated_count")
    if type(value) is int and value >= 0:
        return value
    return source_count


def _hydrate_payload(
    outputs: Mapping[str, Any],
    *,
    source_count: int,
    results: Sequence[Mapping[str, Any]],
    results_omitted: Sequence[Mapping[str, Any]],
    results_omitted_extra: int,
    errors: Sequence[Mapping[str, Any]],
    errors_omitted_count: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "hydrated_count": _canonical_hydrated_count(outputs, source_count=source_count),
        "cap_exceeded": bool(outputs.get("cap_exceeded"))
        if type(outputs.get("cap_exceeded")) is bool
        else False,
        "results": [json_native(dict(row)) for row in results],
        "results_omitted_count": len(results_omitted) + max(0, results_omitted_extra),
    }
    if results_omitted:
        payload["results_omitted"] = [json_native(dict(row)) for row in results_omitted]
    if errors:
        payload["errors"] = [json_native(dict(row)) for row in errors]
    if errors_omitted_count:
        payload["errors_omitted_count"] = int(errors_omitted_count)
    return payload


def _fit_error_rows(
    outputs: Mapping[str, Any],
    *,
    source_count: int,
    results: Sequence[Mapping[str, Any]],
    results_omitted: Sequence[Mapping[str, Any]],
    results_omitted_extra: int,
    error_rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    kept: list[dict[str, Any]] = []
    omitted_count = 0
    for row in error_rows[:MAX_HYDRATE_ERROR_ROWS]:
        trial = kept + [row]
        payload = _hydrate_payload(
            outputs,
            source_count=source_count,
            results=results,
            results_omitted=results_omitted,
            results_omitted_extra=results_omitted_extra,
            errors=trial,
            errors_omitted_count=omitted_count,
        )
        if payload_fits(
            schema_id=SCHEMA_HYDRATE_ARTIFACT_REFS,
            payload=payload,
            continuity_key=None,
        ):
            kept = trial
        else:
            omitted_count += 1
    omitted_count += max(0, len(error_rows) - MAX_HYDRATE_ERROR_ROWS)
    return kept, omitted_count


def _sanitize_error_row(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    row: dict[str, Any] = {}
    code = raw.get("code") or raw.get("reason") or raw.get("reason_code")
    if isinstance(code, str) and code.strip():
        text = code.strip()
        if len(text) <= MAX_ERROR_CODE_CHARS:
            row["code"] = text
        else:
            row["code_omitted"] = True
            row["code_chars"] = len(text)
    ref_id = raw.get("ref_id")
    if isinstance(ref_id, str) and ref_id.strip():
        text = ref_id.strip()
        if len(text) <= MAX_ERROR_REF_ID_CHARS:
            row["ref_id"] = text
        else:
            row["ref_id_omitted"] = True
            row["ref_id_chars"] = len(text)
    message = raw.get("message")
    bound = bound_text(message, field="message") if message is not None else None
    if bound:
        row.update(bound)
    elif isinstance(message, str) and len(message) > MAX_ERROR_MESSAGE_CHARS:
        row["message_omitted"] = True
        row["message_chars"] = len(message)
    return row or None


__all__ = [
    "SCHEMA_HYDRATE_ARTIFACT_REFS",
    "build_hydrate_artifact_refs_view",
]
