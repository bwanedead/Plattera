"""Shared mechanical helpers for deed-to-IR AgentResultView construction."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

from harness.execution.agent_result_view import (
    MAX_CONTINUITY_KEY_CHARS,
    AgentResultView,
    AgentResultViewOmission,
    build_agent_result_view,
)

WORKING_HEAD_CONTINUITY_PREFIX = "deed_to_ir.current_working_head:"
MAX_ERROR_MESSAGE_CHARS = 240
MAX_COLLECTION_ROWS = 32
MAX_REQUESTED_RESOLUTION_UNIT_IDS = 64
MAX_REQUESTED_OPERATION_NAMES = 32
MAX_IGNORED_OPERATION_ROWS = 32

_HOST_OR_BINARY_KEYS = frozenset(
    {
        "absolute_path",
        "path",
        "b64",
        "image_b64",
        "base64",
        "bytes",
        "crop_img",
        "image",
        "image_obj",
    }
)


def build_working_head_continuity_key(
    *,
    dossier_id: str | None,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
) -> str | None:
    """Stable working-head key for one deed-to-IR scope. Never invents from artifact refs."""
    parts = {
        "dossier_id": _nonblank(dossier_id),
        "transcription_id": _nonblank(transcription_id),
        "workspace_id": _nonblank(workspace_id),
        "run_id": _nonblank(run_id),
    }
    if any(value is None for value in parts.values()):
        return None
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    key = f"{WORKING_HEAD_CONTINUITY_PREFIX}{digest}"
    if len(key) > MAX_CONTINUITY_KEY_CHARS:
        return None
    return key


def try_build_view(
    *,
    schema_id: str,
    payload: Mapping[str, Any],
    continuity_key: str | None,
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    cleaned = json_native(strip_host_value(dict(payload)))
    return build_agent_result_view(
        schema_id=schema_id,
        payload=cleaned,
        continuity_key=continuity_key,
    )


def fit_payload_collections(
    *,
    schema_id: str,
    continuity_key: str | None,
    base: Mapping[str, Any],
    collections: Mapping[str, Sequence[Mapping[str, Any]]],
    intake_omitted: Mapping[str, int] | None = None,
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    """Keep identity fields first; greedily add complete collection rows that fit.

    ``intake_omitted`` counts valid rows dropped before fitting (intake cap). Final
    omitted counts satisfy: kept + omitted == original valid row count.
    """
    intake = {key: max(0, int((intake_omitted or {}).get(key) or 0)) for key in collections}
    kept: dict[str, list[dict[str, Any]]] = {key: [] for key in collections}
    omitted: dict[str, int] = {
        key: intake[key] + len(rows) for key, rows in collections.items()
    }

    for key, rows in collections.items():
        for row in rows:
            trial_kept = {k: list(v) for k, v in kept.items()}
            trial_kept[key] = list(kept[key]) + [dict(row)]
            trial_omitted = dict(omitted)
            trial_omitted[key] = intake[key] + (len(rows) - len(trial_kept[key]))
            payload = _assemble(base, trial_kept, trial_omitted)
            view, _ = try_build_view(
                schema_id=schema_id,
                payload=payload,
                continuity_key=continuity_key,
            )
            if view is not None:
                kept = trial_kept
                omitted = trial_omitted

    return try_build_view(
        schema_id=schema_id,
        payload=_assemble(base, kept, omitted),
        continuity_key=continuity_key,
    )


def _assemble(
    base: Mapping[str, Any],
    kept: Mapping[str, Sequence[Mapping[str, Any]]],
    omitted: Mapping[str, int],
) -> dict[str, Any]:
    payload = dict(base)
    for key, rows in kept.items():
        if rows:
            payload[key] = [dict(row) for row in rows]
        count = int(omitted.get(key) or 0)
        if count:
            payload[f"{key}_omitted_count"] = count
    return payload


def json_native(value: Any) -> Any:
    if isinstance(value, tuple):
        return [json_native(item) for item in value]
    if isinstance(value, list):
        return [json_native(item) for item in value]
    if isinstance(value, Mapping):
        return {str(k): json_native(v) for k, v in value.items()}
    return value


def strip_host_fields(value: MutableMapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, item in value.items():
        if str(key) in _HOST_OR_BINARY_KEYS:
            continue
        stripped = strip_host_value(item)
        # Keep empty lists/dicts: successfully hydrated empty sections are valid.
        if stripped is None or stripped == "":
            continue
        out[str(key)] = stripped
    return out


def strip_host_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return strip_host_fields(dict(value))
    if isinstance(value, (list, tuple)):
        return [strip_host_value(item) for item in value]
    return value


def bound_message(message: Any) -> dict[str, Any] | None:
    return bound_text(message, field="message")


def bound_text(value: Any, *, field: str) -> dict[str, Any] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if len(text) <= MAX_ERROR_MESSAGE_CHARS:
        return {field: text}
    return {f"{field}_omitted": True, f"{field}_chars": len(text)}


def copy_scalar_fields(source: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in keys:
        value = source.get(key)
        if value in (None, "", [], (), {}):
            continue
        out[key] = json_native(strip_host_value(value))
    return out


def mapping_rows(
    raw: Any, *, limit: int = MAX_COLLECTION_ROWS
) -> tuple[list[dict[str, Any]], int]:
    """Normalize mapping rows for fitting.

    Explicit rule: non-mapping / malformed items are skipped and do not count
    toward the original valid row total. Intake omission covers valid rows past
    ``limit`` only.
    """
    if not isinstance(raw, list):
        return [], 0
    valid: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        valid.append(json_native(strip_host_fields(dict(item))))
    intake_omitted = max(0, len(valid) - limit)
    return valid[:limit], intake_omitted


def view_budget_omission(*, fields: Sequence[str] | None = None) -> dict[str, Any]:
    marker: dict[str, Any] = {"reason": "view_budget"}
    if fields:
        marker["fields"] = [str(field) for field in fields]
    return marker


def extract_action_inputs(request: Any) -> dict[str, Any] | None:
    """Copy mapping-valued action inputs without mutating or coercing invalid shapes."""
    if hasattr(request, "inputs"):
        raw = getattr(request, "inputs", None)
        if isinstance(raw, Mapping):
            return dict(raw)
        return None
    if isinstance(request, Mapping):
        return dict(request)
    return None


def section_omission(
    *,
    section: str,
    reason: str = "view_budget",
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {"section": str(section), "reason": reason}
    for key, value in extra.items():
        if value is not None:
            row[key] = value
    return row


def string_rows(
    raw: Any, *, limit: int = MAX_COLLECTION_ROWS
) -> tuple[list[str], int]:
    """Whole-string collection intake. Non-strings are skipped and uncounted."""
    if not isinstance(raw, list):
        return [], 0
    valid = [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    intake_omitted = max(0, len(valid) - limit)
    return valid[:limit], intake_omitted


def strict_string_list(raw: Any) -> list[str]:
    """Accept strings only; trim, dedupe, preserve order. Never coerce non-strings."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def bounded_string_ids(
    raw: Any, *, limit: int
) -> tuple[list[str], int]:
    """Strict string IDs with intake omission count. Never substring an ID."""
    ids = strict_string_list(raw)
    omitted = max(0, len(ids) - limit)
    return ids[:limit], omitted


def fit_complete_strings(
    payload: dict[str, Any],
    *,
    schema_id: str,
    key: str,
    values: Sequence[str],
    omitted_key: str,
    intake_limit: int | None = None,
    continuity_key: str | None = None,
) -> None:
    """Fit complete strings; skip oversized; never substring. May omit the field."""
    if not values:
        return
    if intake_limit is None:
        intake = list(values)
        intake_omitted = 0
    else:
        intake = list(values[:intake_limit])
        intake_omitted = max(0, len(values) - intake_limit)

    kept: list[str] = []
    for value in intake:
        trial = list(kept) + [value]
        trial_omitted = intake_omitted + (len(intake) - len(trial))
        candidate = {**payload, key: trial}
        if trial_omitted:
            candidate[omitted_key] = trial_omitted
        if payload_fits(
            schema_id=schema_id, payload=candidate, continuity_key=continuity_key
        ):
            kept = trial
            continue
        continue

    omitted = intake_omitted + (len(intake) - len(kept))
    if kept:
        payload[key] = kept
    if omitted:
        count_candidate = {**payload, omitted_key: omitted}
        if payload_fits(
            schema_id=schema_id,
            payload=count_candidate,
            continuity_key=continuity_key,
        ):
            payload[omitted_key] = omitted


def bounded_ignored_operation_rows(
    raw: Any, *, limit: int = MAX_IGNORED_OPERATION_ROWS
) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(raw, list):
        return [], 0
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name")
        reason = item.get("reason")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(reason, str) or not reason.strip():
            continue
        rows.append({"name": name.strip(), "reason": reason.strip()})
    omitted = max(0, len(rows) - limit)
    return rows[:limit], omitted


def payload_fits(
    *,
    schema_id: str,
    payload: Mapping[str, Any],
    continuity_key: str | None = None,
) -> bool:
    view, _ = try_build_view(
        schema_id=schema_id,
        payload=payload,
        continuity_key=continuity_key,
    )
    return view is not None


def try_attach_value(
    payload: dict[str, Any],
    *,
    key: str,
    value: Any,
    schema_id: str,
    continuity_key: str | None = None,
) -> bool:
    trial = dict(payload)
    trial[key] = value
    if not payload_fits(schema_id=schema_id, payload=trial, continuity_key=continuity_key):
        return False
    payload[key] = value
    return True


def _nonblank(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
