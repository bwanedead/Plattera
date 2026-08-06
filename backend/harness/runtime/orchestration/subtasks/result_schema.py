"""Schema-driven validation and normalization for delegated subtask results."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .contracts import SubtaskProfile

_MAX_FIELD_CHARS = 1_200
_MAX_LIST_ITEMS = 6
_MAX_NESTED_DEPTH = 2
_MAX_RESULT_FIELDS = 16
_PRIMITIVE_MARKERS = frozenset({"string", "string|null"})
_BINARY_KEY_PARTS = ("b64", "base64", "bytes", "binary")
_FORBIDDEN_FIELD_NAMES = frozenset({"confidence"})


class SubtaskProfileSchemaError(ValueError):
    """Raised when a profile ``result_schema`` is mechanically invalid."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class SubtaskResultSchemaError(ValueError):
    """Raised when child output does not match the profile result schema."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def validate_profile_result_schema(schema: Mapping[str, Any]) -> None:
    """Validate a profile result schema at registration time."""

    if not isinstance(schema, Mapping):
        raise SubtaskProfileSchemaError(
            "result_schema_invalid",
            "subtask profile result_schema must be an object",
        )
    if _contains_forbidden_key(schema):
        raise SubtaskProfileSchemaError(
            "result_schema_confidence_disallowed",
            "subtask profile result_schema must not include confidence fields",
        )
    if _contains_binary_key(schema):
        raise SubtaskProfileSchemaError(
            "result_schema_binary_field_disallowed",
            "subtask profile result_schema must not include binary/raw payload fields",
        )
    status_spec = schema.get("status")
    if not _is_enum_spec(status_spec):
        raise SubtaskProfileSchemaError(
            "result_schema_status_invalid",
            "subtask profile result_schema.status must be a non-empty enum list",
        )
    result_spec = schema.get("result")
    if not isinstance(result_spec, Mapping):
        raise SubtaskProfileSchemaError(
            "result_schema_result_invalid",
            "subtask profile result_schema.result must be an object",
        )
    if len(result_spec) > _MAX_RESULT_FIELDS:
        raise SubtaskProfileSchemaError(
            "result_schema_result_too_many_fields",
            f"subtask profile result_schema.result exceeds field cap {_MAX_RESULT_FIELDS}",
        )
    for field_name, field_spec in result_spec.items():
        name = str(field_name or "").strip()
        if not name:
            raise SubtaskProfileSchemaError(
                "result_schema_result_field_invalid",
                "subtask profile result_schema.result contains an empty field name",
            )
        if name.lower() in _FORBIDDEN_FIELD_NAMES:
            raise SubtaskProfileSchemaError(
                "result_schema_confidence_disallowed",
                "subtask profile result_schema must not include confidence fields",
            )
        if _is_binary_key(name):
            raise SubtaskProfileSchemaError(
                "result_schema_binary_field_disallowed",
                "subtask profile result_schema must not include binary/raw payload fields",
            )
        _validate_type_spec(field_spec, path=f"result.{name}", depth=0)


def normalize_result_payload(
    raw: Mapping[str, Any],
    *,
    profile: SubtaskProfile,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Normalize child ``result`` payload according to ``profile.result_schema``.

    Returns ``(normalized_result, truncation_meta)`` where ``truncation_meta`` is
    ``None`` when no size truncation was applied.
    """

    schema = profile.result_schema if isinstance(profile.result_schema, Mapping) else {}
    result_spec = schema.get("result")
    if not isinstance(result_spec, Mapping):
        raise SubtaskResultSchemaError(
            "subtask_result_schema_invalid",
            "Profile result schema is missing a result object.",
        )
    sanitized_raw = _strip_forbidden_keys(dict(raw))
    normalized = _normalize_object(sanitized_raw, result_spec, path="result")
    return _cap_result_size(
        normalized,
        max_chars=profile.max_result_chars,
        result_spec=result_spec,
    )


def empty_result_for_profile(
    profile: SubtaskProfile,
    *,
    message: str | None = None,
) -> dict[str, Any]:
    """Build schema-shaped empty defaults for failed subtask results."""

    schema = profile.result_schema if isinstance(profile.result_schema, Mapping) else {}
    result_spec = schema.get("result")
    if not isinstance(result_spec, Mapping):
        return {
            "reading": None,
            "ambiguity": "",
            "observations": [],
            "limits": [_bound_text(message or "Subtask failed.", _MAX_FIELD_CHARS)],
        }
    out = _failed_empty_object(result_spec)
    if message and "limits" in out and isinstance(out["limits"], list):
        out["limits"] = [_bound_text(message, _MAX_FIELD_CHARS)]
    return out


def project_result_payload(
    result: Mapping[str, Any],
    *,
    result_schema: Mapping[str, Any],
    max_chars: int = 700,
) -> dict[str, Any]:
    """Project a normalized result payload into audit-safe bounded form."""

    result_spec = result_schema.get("result")
    if not isinstance(result_spec, Mapping):
        return _project_fallback(result)
    projected = _project_object(result, result_spec)
    capped, _ = _cap_result_size(projected, max_chars=max_chars, result_spec=result_spec)
    return capped


def _validate_type_spec(spec: Any, *, path: str, depth: int) -> None:
    if _is_primitive_spec(spec):
        return
    if _is_list_spec(spec):
        return
    if _is_enum_spec(spec):
        return
    if isinstance(spec, Mapping):
        if depth >= _MAX_NESTED_DEPTH:
            raise SubtaskProfileSchemaError(
                "result_schema_nested_depth_exceeded",
                f"subtask profile result_schema nested depth exceeds cap at {path}",
            )
        if len(spec) > _MAX_RESULT_FIELDS:
            raise SubtaskProfileSchemaError(
                "result_schema_result_too_many_fields",
                f"subtask profile result_schema object at {path} exceeds field cap",
            )
        for field_name, field_spec in spec.items():
            name = str(field_name or "").strip()
            if not name:
                raise SubtaskProfileSchemaError(
                    "result_schema_result_field_invalid",
                    f"subtask profile result_schema contains empty field at {path}",
                )
            if name.lower() in _FORBIDDEN_FIELD_NAMES:
                raise SubtaskProfileSchemaError(
                    "result_schema_confidence_disallowed",
                    "subtask profile result_schema must not include confidence fields",
                )
            if _is_binary_key(name):
                raise SubtaskProfileSchemaError(
                    "result_schema_binary_field_disallowed",
                    "subtask profile result_schema must not include binary/raw payload fields",
                )
            _validate_type_spec(field_spec, path=f"{path}.{name}", depth=depth + 1)
        return
    raise SubtaskProfileSchemaError(
        "result_schema_type_unsupported",
        f"subtask profile result_schema contains unsupported type at {path}",
    )


def _normalize_object(
    raw: Mapping[str, Any],
    spec: Mapping[str, Any],
    *,
    path: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field_name, field_spec in spec.items():
        name = str(field_name)
        out[name] = _normalize_value(raw.get(name), field_spec, path=f"{path}.{name}")
    return out


def _normalize_value(value: Any, spec: Any, *, path: str) -> Any:
    if value is None:
        if _is_primitive_spec(spec):
            if spec == "string|null":
                return None
            return ""
        if _is_list_spec(spec):
            return []
        if _is_enum_spec(spec):
            raise SubtaskResultSchemaError(
                "subtask_result_field_invalid",
                f"Expected enum value at {path}.",
            )
        if isinstance(spec, Mapping):
            # Successful normalization must still require nested enums; do not use
            # framework-failure defaults (which omit enums) on this path.
            return _normalize_object({}, spec, path=path)
    if _is_primitive_spec(spec):
        return _normalize_primitive(value, spec, path=path)
    if _is_list_spec(spec):
        return _normalize_string_list(value, path=path)
    if _is_enum_spec(spec):
        return _normalize_enum(value, spec, path=path)
    if isinstance(spec, Mapping):
        if not isinstance(value, Mapping):
            if value is None:
                return _normalize_object({}, spec, path=path)
            raise SubtaskResultSchemaError(
                "subtask_result_field_invalid",
                f"Expected object at {path}.",
            )
        return _normalize_object(value, spec, path=path)
    raise SubtaskResultSchemaError(
        "subtask_result_schema_invalid",
        f"Unsupported schema type at {path}.",
    )


def _normalize_primitive(value: Any, spec: str, *, path: str) -> str | None:
    if spec == "string|null":
        if value is None:
            return None
        if not isinstance(value, str):
            raise SubtaskResultSchemaError(
                "subtask_result_field_invalid",
                f"Expected string or null at {path}.",
            )
        return _bound_text(value, _MAX_FIELD_CHARS)
    if not isinstance(value, str):
        raise SubtaskResultSchemaError(
            "subtask_result_field_invalid",
            f"Expected string at {path}.",
        )
    return _bound_text(value, _MAX_FIELD_CHARS)


def _normalize_string_list(value: Any, *, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise SubtaskResultSchemaError(
            "subtask_result_field_invalid",
            f"Expected string list at {path}.",
        )
    out: list[str] = []
    for index, item in enumerate(value[: _MAX_LIST_ITEMS]):
        if not isinstance(item, str):
            raise SubtaskResultSchemaError(
                "subtask_result_field_invalid",
                f"Expected string list item at {path}[{index}].",
            )
        text = str(item).strip()
        if text:
            out.append(_bound_text(text, _MAX_FIELD_CHARS))
    return out


def _normalize_enum(value: Any, spec: list[Any], *, path: str) -> str:
    allowed = {str(item).strip() for item in spec if str(item).strip()}
    text = str(value or "").strip()
    if text not in allowed:
        raise SubtaskResultSchemaError(
            "subtask_result_field_invalid",
            f"Value at {path} must be one of: {', '.join(sorted(allowed))}.",
        )
    return text


def _failed_empty_object(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Build empty defaults for framework-generated failed results only.

    Enum-valued fields are omitted recursively rather than inventing a first-member
    observation. Successful child-result normalization must not call this helper.
    """
    out: dict[str, Any] = {}
    for field_name, field_spec in spec.items():
        name = str(field_name)
        if _is_enum_spec(field_spec):
            continue
        out[name] = _failed_empty_value(field_spec)
    return out


def _failed_empty_value(spec: Any) -> Any:
    if spec == "string|null":
        return None
    if spec == "string":
        return ""
    if _is_list_spec(spec):
        return []
    if _is_enum_spec(spec):
        # Framework-generated failures must not invent enum observations.
        # Callers should omit enum fields via ``_failed_empty_object``.
        raise AssertionError("enum defaults must be omitted, not invented")
    if isinstance(spec, Mapping):
        return _failed_empty_object(spec)
    return ""


def _project_object(result: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field_name, field_spec in spec.items():
        name = str(field_name)
        if name not in result:
            continue
        out[name] = _project_value(result.get(name), field_spec)
    return out


def _project_value(value: Any, spec: Any) -> Any:
    if _is_primitive_spec(spec):
        if spec == "string|null":
            return _nullable_short(value)
        return _short(value)
    if _is_list_spec(spec):
        if not isinstance(value, (list, tuple)):
            return []
        return [_short(item) for item in value[:4] if str(item or "").strip()]
    if _is_enum_spec(spec):
        return _short(value)
    if isinstance(spec, Mapping) and isinstance(value, Mapping):
        return _project_object(value, spec)
    return _short(value)


def _project_fallback(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _short(value) if not isinstance(value, list) else [_short(item) for item in value[:4]]
        for key, value in result.items()
        if not _is_binary_key(str(key))
    }


def _cap_result_size(
    result: dict[str, Any],
    *,
    max_chars: int,
    result_spec: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    original_chars = _json_len(result)
    if original_chars <= int(max_chars):
        return result, None

    protected_keys = _enum_field_names(result_spec) if isinstance(result_spec, Mapping) else frozenset()
    shrunk = _shrink_result(result, protected_keys=protected_keys)
    if _json_len(shrunk) <= int(max_chars):
        return shrunk, _truncation_meta(result, shrunk, original_chars=original_chars)

    aggressive = _aggressive_cap_result(
        shrunk,
        max_chars=int(max_chars),
        protected_keys=protected_keys,
    )
    return aggressive, _truncation_meta(result, aggressive, original_chars=original_chars)


def _truncation_meta(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    original_chars: int,
) -> dict[str, Any]:
    fields = _diff_truncated_fields(before, after)
    return {
        "result_truncated": True,
        "truncated_fields": fields,
        "original_result_chars": int(original_chars),
    }


def _diff_truncated_fields(before: Mapping[str, Any], after: Mapping[str, Any], *, prefix: str = "") -> list[str]:
    fields: list[str] = []
    keys = sorted(set(before.keys()) | set(after.keys()))
    for key in keys:
        path = f"{prefix}.{key}" if prefix else str(key)
        if key not in after:
            if key in before:
                fields.append(path)
            continue
        if key not in before:
            continue
        before_value = before.get(key)
        after_value = after.get(key)
        if isinstance(before_value, str) and isinstance(after_value, str):
            if len(after_value) < len(before_value.strip()):
                fields.append(path)
            continue
        if isinstance(before_value, list) and isinstance(after_value, list):
            for index, (before_item, after_item) in enumerate(zip(before_value, after_value)):
                item_path = f"{path}[{index}]"
                if isinstance(before_item, str) and isinstance(after_item, str):
                    if len(after_item) < len(before_item.strip()):
                        fields.append(item_path)
                elif isinstance(before_item, Mapping) and isinstance(after_item, Mapping):
                    fields.extend(_diff_truncated_fields(before_item, after_item, prefix=item_path))
            if len(after_value) < len(before_value):
                fields.append(path)
            continue
        if isinstance(before_value, Mapping) and isinstance(after_value, Mapping):
            fields.extend(_diff_truncated_fields(before_value, after_value, prefix=path))
    return fields


def _aggressive_cap_result(
    result: dict[str, Any],
    *,
    max_chars: int,
    protected_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    capped = _shrink_result(result, protected_keys=protected_keys)
    guard = 0
    while _json_len(capped) > int(max_chars) and guard < 48:
        guard += 1
        longest_key = None
        longest_len = -1
        for key, value in capped.items():
            if key in protected_keys:
                continue
            if isinstance(value, str) and len(value) > longest_len:
                longest_key = key
                longest_len = len(value)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if isinstance(item, str) and len(item) > longest_len:
                        longest_key = f"{key}[{index}]"
                        longest_len = len(item)
        if longest_key is None or longest_len <= 8:
            break
        if "[" in longest_key:
            list_key, index_text = longest_key.split("[", 1)
            index = int(index_text.rstrip("]"))
            items = capped.get(list_key)
            if isinstance(items, list) and 0 <= index < len(items) and isinstance(items[index], str):
                items[index] = items[index][: max(8, len(items[index]) // 2)]
            continue
        if isinstance(capped.get(longest_key), str):
            text = str(capped[longest_key])
            capped[longest_key] = text[: max(8, len(text) // 2)]
    if _json_len(capped) > int(max_chars):
        capped = _minimal_cap_result(
            capped,
            max_chars=int(max_chars),
            protected_keys=protected_keys,
        )
    # Absolute serialized cap: never return an over-budget object.
    if _json_len(capped) > int(max_chars):
        capped = {}
    return capped


def _minimal_cap_result(
    result: dict[str, Any],
    *,
    max_chars: int,
    protected_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Build a budget-fitting result without substring-truncating protected enums.

    Protected enum values are kept whole when they fit, omitted whole when they do
    not, and never substring-truncated. The returned object always respects
    ``max_chars``.
    """
    minimal: dict[str, Any] = {}
    # Prefer schema/result order so earlier packet-outcome enums survive first.
    for key in result:
        if key not in protected_keys:
            continue
        candidate = {**minimal, key: result[key]}
        if _json_len(candidate) <= int(max_chars):
            minimal[key] = result[key]
        # else: omit the whole protected field; never substring-truncate it.
    for key, value in result.items():
        if key in protected_keys:
            continue
        if _json_len({**minimal, key: value}) > int(max_chars):
            if isinstance(value, str):
                remaining = int(max_chars) - _json_len(minimal) - len(str(key)) - 6
                if remaining > 8:
                    partial = {**minimal, key: value[:remaining]}
                    if _json_len(partial) <= int(max_chars):
                        minimal[key] = value[:remaining]
            elif isinstance(value, list) and value:
                remaining = int(max_chars) - _json_len(minimal) - len(str(key)) - 8
                if remaining > 8 and isinstance(value[0], str):
                    partial = {**minimal, key: [value[0][:remaining]]}
                    if _json_len(partial) <= int(max_chars):
                        minimal[key] = [value[0][:remaining]]
            continue
        minimal[key] = value
        if _json_len(minimal) >= int(max_chars):
            break
    return minimal


def _short_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return value[:80]
    if isinstance(value, list):
        return [_short_scalar(item) for item in value[:2]]
    return value


def _json_len(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, separators=(",", ":"), default=str))


def _shrink_result(
    result: dict[str, Any],
    *,
    protected_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    capped: dict[str, Any] = {}
    for key, value in result.items():
        if key in protected_keys:
            capped[key] = value
            continue
        if isinstance(value, str):
            capped[key] = value[:120]
        elif isinstance(value, list):
            capped[key] = [
                item[:120] if isinstance(item, str) else item
                for item in value[:2]
            ]
        elif isinstance(value, Mapping):
            capped[key] = {
                inner_key: inner_value[:120] if isinstance(inner_value, str) else inner_value
                for inner_key, inner_value in list(value.items())[:4]
            }
        else:
            capped[key] = value
    return capped


def _enum_field_names(spec: Mapping[str, Any] | None) -> frozenset[str]:
    """Top-level enum field names that must not be substring-truncated under budget pressure."""
    if not isinstance(spec, Mapping):
        return frozenset()
    return frozenset(
        str(field_name)
        for field_name, field_spec in spec.items()
        if _is_enum_spec(field_spec)
    )


def _is_primitive_spec(spec: Any) -> bool:
    return isinstance(spec, str) and spec in _PRIMITIVE_MARKERS


def _is_list_spec(spec: Any) -> bool:
    return (
        isinstance(spec, (list, tuple))
        and len(spec) == 1
        and isinstance(spec[0], str)
        and spec[0] in _PRIMITIVE_MARKERS
    )


def _is_enum_spec(spec: Any) -> bool:
    if not isinstance(spec, (list, tuple)) or not spec:
        return False
    if len(spec) == 1 and isinstance(spec[0], str) and spec[0] in _PRIMITIVE_MARKERS:
        return False
    return all(isinstance(item, str) and item.strip() for item in spec)


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, inner in value.items():
            if str(key).strip().lower() in _FORBIDDEN_FIELD_NAMES:
                return True
            if _contains_forbidden_key(inner):
                return True
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _contains_binary_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, inner in value.items():
            if _is_binary_key(str(key)):
                return True
            if _contains_binary_key(inner):
                return True
    if isinstance(value, (list, tuple)):
        return any(_contains_binary_key(item) for item in value)
    return False


def _strip_forbidden_keys(raw: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in raw.items():
        name = str(key)
        if name.lower() in _FORBIDDEN_FIELD_NAMES or _is_binary_key(name):
            continue
        if isinstance(value, Mapping):
            out[name] = _strip_forbidden_keys(value)
        elif isinstance(value, list):
            out[name] = [
                _strip_forbidden_keys(item) if isinstance(item, Mapping) else item
                for item in value
            ]
        else:
            out[name] = value
    return out


def _is_binary_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in _BINARY_KEY_PARTS)


def _bound_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= int(limit):
        return text
    return text[: int(limit)]


def _short(value: Any) -> str:
    return _bound_text(value, _MAX_FIELD_CHARS)


def _nullable_short(value: Any) -> str | None:
    if value is None:
        return None
    return _short(value)
