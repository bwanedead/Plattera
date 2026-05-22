"""Schema-driven validation and normalization for delegated subtask results."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .contracts import SubtaskProfile

_MAX_FIELD_CHARS = 240
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
) -> dict[str, Any]:
    """Normalize child ``result`` payload according to ``profile.result_schema``."""

    schema = profile.result_schema if isinstance(profile.result_schema, Mapping) else {}
    result_spec = schema.get("result")
    if not isinstance(result_spec, Mapping):
        raise SubtaskResultSchemaError(
            "subtask_result_schema_invalid",
            "Profile result schema is missing a result object.",
        )
    sanitized_raw = _strip_forbidden_keys(dict(raw))
    normalized = _normalize_object(sanitized_raw, result_spec, path="result")
    return _cap_result_size(normalized, max_chars=profile.max_result_chars)


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
    out = _empty_object(result_spec)
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
    return _cap_result_size(projected, max_chars=max_chars)


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
            return _empty_object(spec)
    if _is_primitive_spec(spec):
        return _normalize_primitive(value, spec, path=path)
    if _is_list_spec(spec):
        return _normalize_string_list(value, path=path)
    if _is_enum_spec(spec):
        return _normalize_enum(value, spec, path=path)
    if isinstance(spec, Mapping):
        if not isinstance(value, Mapping):
            if value is None:
                return _empty_object(spec)
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


def _empty_object(spec: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field_name, field_spec in spec.items():
        name = str(field_name)
        out[name] = _empty_value(field_spec)
    return out


def _empty_value(spec: Any) -> Any:
    if spec == "string|null":
        return None
    if spec == "string":
        return ""
    if _is_list_spec(spec):
        return []
    if _is_enum_spec(spec):
        return str(spec[0])
    if isinstance(spec, Mapping):
        return _empty_object(spec)
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


def _cap_result_size(result: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    text = json.dumps(result, separators=(",", ":"), default=str)
    if len(text) <= int(max_chars):
        return result
    capped = _shrink_result(result)
    text = json.dumps(capped, separators=(",", ":"), default=str)
    if len(text) <= int(max_chars):
        return capped
    raise SubtaskResultSchemaError(
        "subtask_result_too_large",
        f"Normalized subtask result exceeds max size {int(max_chars)}.",
    )


def _shrink_result(result: dict[str, Any]) -> dict[str, Any]:
    capped: dict[str, Any] = {}
    for key, value in result.items():
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
