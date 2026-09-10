"""Canonical bounded error lanes for host hydration continuity.

Sanitizes resolution/hydration errors before storage and prompt projection.
Raw provider/tool error payloads never enter continuity directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.runtime.memory.result_representation import (
    contains_host_or_binary_fields,
    is_json_safe,
    measure_compact_json_chars,
)

MAX_HYDRATION_ERROR_ROWS = 16
MAX_ERROR_REASON_CODE_CHARS = 128
MAX_ERROR_IDENTITY_CHARS = 256
MAX_ERROR_VALID_REPLACEMENTS = 4
MAX_ERROR_LANE_SERIALIZED_CHARS = 6_000
MAX_ERROR_MESSAGE_KEEP_CHARS = 400

_ALLOWED_STORED_ERROR_KEYS = frozenset(
    {
        "reason_code",
        "requested_ref",
        "source_action_alias",
        "source_action_type",
        "hydration_optional",
        "valid_replacements",
        "hint",
        "message_omitted",
        "message_chars",
        "hint_omitted",
        "hint_chars",
        "fields_omitted_count",
    }
)

_IDENTITY_KEYS = ("requested_ref", "source_action_alias", "source_action_type")


def project_hydration_error_lane(raw: Any) -> tuple[list[dict[str, Any]], int]:
    """Sanitize raw error rows for storage/projection.

    Returns ``(rows, rows_omitted_count)``. Never substring-truncates messages;
    long or unsafe prose becomes omission metadata.
    """
    if raw is None:
        return [], 0
    if not isinstance(raw, (list, tuple)):
        return (
            [
                {
                    "reason_code": "hydration_error_lane_invalid",
                    "fields_omitted_count": 1,
                }
            ],
            0,
        )

    projected: list[dict[str, Any]] = []
    omitted_rows = 0
    for index, item in enumerate(raw):
        if len(projected) >= MAX_HYDRATION_ERROR_ROWS:
            omitted_rows += len(raw) - index
            break
        row = _project_one_error_row(item)
        if row is None:
            omitted_rows += 1
            continue
        candidate = list(projected) + [row]
        try:
            chars = measure_compact_json_chars(candidate)
        except (TypeError, ValueError):
            omitted_rows += 1
            continue
        if chars > MAX_ERROR_LANE_SERIALIZED_CHARS:
            omitted_rows += len(raw) - index
            break
        projected.append(row)
    return projected, omitted_rows


def validate_stored_hydration_error_lane(raw: Any) -> list[dict[str, Any]] | None:
    """Strict resume validator. ``None`` means refuse the parent record."""
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    if len(raw) > MAX_HYDRATION_ERROR_ROWS:
        return None
    out: list[dict[str, Any]] = []
    for item in raw:
        validated = _validate_one_stored_error_row(item)
        if validated is None:
            return None
        out.append(validated)
    try:
        if measure_compact_json_chars(out) > MAX_ERROR_LANE_SERIALIZED_CHARS:
            return None
    except (TypeError, ValueError):
        return None
    return out


def validate_optional_hydration_error_lane(raw: Any) -> list[dict[str, Any]] | None | bool:
    """Resume helper: ``None`` input stays ``None``; invalid → ``False``; else list."""
    if raw is None:
        return None
    validated = validate_stored_hydration_error_lane(raw)
    if validated is None:
        return False
    return validated


def omit_error_lane_details(
    lane: dict[str, Any],
    *,
    errors_key: str,
    omitted_count_key: str,
) -> dict[str, Any]:
    """Replace error detail whole with explicit omission counts + stable reason codes."""
    out = dict(lane)
    rows = out.pop(errors_key, None)
    codes: list[str] = []
    omitted = int(out.get(omitted_count_key) or 0)
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                code = row.get("reason_code")
                if isinstance(code, str) and code and len(codes) < MAX_HYDRATION_ERROR_ROWS:
                    codes.append(code)
        omitted += len(rows)
    if omitted > 0:
        out[omitted_count_key] = omitted
    elif omitted_count_key in out:
        out.pop(omitted_count_key, None)
    if codes:
        # Compact stable codes only (already bounded length per row).
        key = f"{errors_key}_reason_codes"
        out[key] = codes[:MAX_HYDRATION_ERROR_ROWS]
    return out


def _project_one_error_row(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if len(text) <= MAX_ERROR_REASON_CODE_CHARS and text == raw.strip():
            # Treat short bare strings as reason codes only when already stripped.
            return {"reason_code": text}
        return {
            "reason_code": "hydration_error",
            "message_omitted": True,
            "message_chars": len(raw),
        }
    if not isinstance(raw, Mapping):
        return {"reason_code": "hydration_error", "fields_omitted_count": 1}
    if not is_json_safe(dict(raw)):
        return {
            "reason_code": "hydration_error_not_json_safe",
            "fields_omitted_count": 1,
        }

    fields_omitted = 0
    reason_raw = raw.get("reason_code")
    if type(reason_raw) is not str or not reason_raw.strip() or reason_raw.strip() != reason_raw:
        reason_code = "hydration_error"
        fields_omitted += 1
    else:
        reason_code = reason_raw
        if len(reason_code) > MAX_ERROR_REASON_CODE_CHARS:
            return {
                "reason_code": "hydration_error",
                "message_omitted": True,
                "message_chars": len(reason_code),
                "fields_omitted_count": 1,
            }

    out: dict[str, Any] = {"reason_code": reason_code}

    for key in _IDENTITY_KEYS:
        if key not in raw:
            continue
        value = raw.get(key)
        if value is None:
            continue
        if type(value) is not str or not value or value.strip() != value:
            fields_omitted += 1
            continue
        if len(value) > MAX_ERROR_IDENTITY_CHARS:
            fields_omitted += 1
            continue
        out[key] = value

    if "hydration_optional" in raw:
        flag = raw.get("hydration_optional")
        if type(flag) is bool:
            out["hydration_optional"] = flag
        else:
            fields_omitted += 1

    if "valid_replacements" in raw:
        reps_raw = raw.get("valid_replacements")
        if isinstance(reps_raw, (list, tuple)):
            reps: list[str] = []
            for item in reps_raw:
                if type(item) is not str or not item or item.strip() != item:
                    fields_omitted += 1
                    continue
                if len(item) > MAX_ERROR_IDENTITY_CHARS:
                    fields_omitted += 1
                    continue
                if len(reps) < MAX_ERROR_VALID_REPLACEMENTS:
                    reps.append(item)
                else:
                    fields_omitted += 1
            if reps:
                out["valid_replacements"] = reps
        else:
            fields_omitted += 1

    # Long/unsafe prose fields: omit whole with metadata (never substring).
    # Short JSON-safe prose may be retained; host/binary keys never are.
    for prose_key, omitted_key, chars_key in (
        ("hint", "hint_omitted", "hint_chars"),
        ("message", "message_omitted", "message_chars"),
        ("detail", "message_omitted", "message_chars"),
        ("error", "message_omitted", "message_chars"),
    ):
        if prose_key not in raw:
            continue
        value = raw.get(prose_key)
        if value is None:
            continue
        if type(value) is not str:
            fields_omitted += 1
            continue
        if contains_host_or_binary_fields({prose_key: value}):
            fields_omitted += 1
            out[omitted_key] = True
            out[chars_key] = len(value)
            continue
        if len(value) > MAX_ERROR_MESSAGE_KEEP_CHARS:
            out[omitted_key] = True
            out[chars_key] = len(value)
            continue
        # Keep short safe prose under an allowed stored key.
        if prose_key == "hint":
            out["hint"] = value
        else:
            # Collapse message/detail/error into omission metadata only —
            # resolution hints are the one intentional short-prose lane.
            out[omitted_key] = True
            out[chars_key] = len(value)

    # Strip unknown / host / binary keys by omission count (do not copy).
    for key, value in raw.items():
        if key in _ALLOWED_STORED_ERROR_KEYS or key in {
            "hint",
            "message",
            "detail",
            "error",
            "reason_code",
            "requested_ref",
            "source_action_alias",
            "source_action_type",
            "hydration_optional",
            "valid_replacements",
        }:
            continue
        fields_omitted += 1
        if isinstance(key, str) and contains_host_or_binary_fields({key: value}):
            continue

    if fields_omitted > 0:
        out["fields_omitted_count"] = int(fields_omitted)
    return out


def _validate_one_stored_error_row(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    if any(key not in _ALLOWED_STORED_ERROR_KEYS for key in raw.keys()):
        return None
    reason_code = raw.get("reason_code")
    if type(reason_code) is not str or not reason_code or reason_code.strip() != reason_code:
        return None
    if len(reason_code) > MAX_ERROR_REASON_CODE_CHARS:
        return None
    out: dict[str, Any] = {"reason_code": reason_code}

    for key in _IDENTITY_KEYS:
        if key not in raw:
            continue
        value = raw.get(key)
        if type(value) is not str or not value or value.strip() != value:
            return None
        if len(value) > MAX_ERROR_IDENTITY_CHARS:
            return None
        out[key] = value

    if "hydration_optional" in raw:
        if type(raw.get("hydration_optional")) is not bool:
            return None
        out["hydration_optional"] = raw.get("hydration_optional")

    if "valid_replacements" in raw:
        reps = raw.get("valid_replacements")
        if not isinstance(reps, list) or len(reps) > MAX_ERROR_VALID_REPLACEMENTS:
            return None
        cleaned: list[str] = []
        for item in reps:
            if type(item) is not str or not item or item.strip() != item:
                return None
            if len(item) > MAX_ERROR_IDENTITY_CHARS:
                return None
            cleaned.append(item)
        out["valid_replacements"] = cleaned

    if "hint" in raw:
        if "hint_omitted" in raw or "hint_chars" in raw:
            return None
        hint = raw.get("hint")
        if type(hint) is not str or not hint or hint.strip() != hint:
            return None
        if len(hint) > MAX_ERROR_MESSAGE_KEEP_CHARS:
            return None
        if contains_host_or_binary_fields({"hint": hint}):
            return None
        out["hint"] = hint

    for flag_key, chars_key in (
        ("message_omitted", "message_chars"),
        ("hint_omitted", "hint_chars"),
    ):
        has_flag = flag_key in raw
        has_chars = chars_key in raw
        if has_flag != has_chars:
            return None
        if not has_flag:
            continue
        if raw.get(flag_key) is not True:
            return None
        chars = raw.get(chars_key)
        if type(chars) is not int or chars <= 0:
            return None
        out[flag_key] = True
        out[chars_key] = chars

    if "fields_omitted_count" in raw:
        count = raw.get("fields_omitted_count")
        if type(count) is not int or count <= 0:
            return None
        out["fields_omitted_count"] = count

    if contains_host_or_binary_fields(out):
        return None
    if not is_json_safe(out):
        return None
    return out


__all__ = [
    "MAX_ERROR_LANE_SERIALIZED_CHARS",
    "MAX_HYDRATION_ERROR_ROWS",
    "omit_error_lane_details",
    "project_hydration_error_lane",
    "validate_optional_hydration_error_lane",
    "validate_stored_hydration_error_lane",
]
