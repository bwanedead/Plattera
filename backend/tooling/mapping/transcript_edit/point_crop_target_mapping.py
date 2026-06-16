"""Deterministic point-crop ↔ resolution-atom target mapping (exact IDs only)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_TARGET_ID_CHARS = 128
MAX_TARGET_HINT_CHARS = 120
DEFAULT_TARGET_HINT_ROLE = "candidate_only_not_earned"
ALLOWED_TARGET_HINT_ROLES = frozenset({DEFAULT_TARGET_HINT_ROLE})

TARGET_MAPPING_KEYS = (
    "target_atom_id",
    "target_context_id",
    "target_hint",
    "target_hint_role",
)


def copy_target_mapping_fields(source: Mapping[str, Any]) -> dict[str, Any]:
    """Copy normalized target-mapping fields when present on a point record."""
    out: dict[str, Any] = {}
    for key in TARGET_MAPPING_KEYS:
        value = source.get(key)
        if key in ("target_atom_id", "target_context_id", "target_hint", "target_hint_role"):
            if isinstance(value, str) and value.strip():
                out[key] = value.strip()
    return out


def normalize_target_mapping_fields(
    raw: Mapping[str, Any],
    *,
    field_prefix: str,
    keys_to_apply: set[str] | None = None,
) -> dict[str, Any]:
    """Validate and normalize optional target-mapping fields from one point/adjust object."""
    keys = keys_to_apply if keys_to_apply is not None else {k for k in TARGET_MAPPING_KEYS if k in raw}
    if not keys:
        return {}

    out: dict[str, Any] = {}

    if "target_atom_id" in keys:
        atom_id = _normalize_id(raw.get("target_atom_id"), field=f"{field_prefix}.target_atom_id")
        if atom_id:
            out["target_atom_id"] = atom_id

    if "target_context_id" in keys:
        context_id = _normalize_id(
            raw.get("target_context_id"),
            field=f"{field_prefix}.target_context_id",
        )
        if context_id:
            out["target_context_id"] = context_id

    hint: str | None = None
    if "target_hint" in keys:
        hint = _normalize_hint(raw.get("target_hint"), field=f"{field_prefix}.target_hint")
        if hint:
            out["target_hint"] = hint

    if "target_hint_role" in keys:
        role = _normalize_hint_role(
            raw.get("target_hint_role"),
            field=f"{field_prefix}.target_hint_role",
        )
        if role:
            out["target_hint_role"] = role
    elif hint:
        out["target_hint_role"] = DEFAULT_TARGET_HINT_ROLE

    if "target_hint_role" in out and "target_hint" not in out and "target_hint" not in keys:
        _raise_param_error(
            f"{field_prefix}.target_hint_role requires target_hint on the same point.",
        )

    return out


def apply_target_mapping_to_point(
    point: dict[str, Any],
    raw: Mapping[str, Any],
    *,
    field_prefix: str,
    allow_clear: bool = False,
) -> None:
    """Merge or clear target-mapping fields on an in-memory point row."""
    keys_present = {k for k in TARGET_MAPPING_KEYS if k in raw}
    if not keys_present:
        return

    clears = {k for k in keys_present if raw.get(k) is None}
    if clears:
        if not allow_clear:
            _raise_param_error(
                f"{field_prefix} does not support null clears for target mapping fields.",
            )
        for key in clears:
            point.pop(key, None)
        if "target_hint" in clears:
            point.pop("target_hint_role", None)
        keys_present -= clears

    normalized = normalize_target_mapping_fields(
        raw,
        field_prefix=field_prefix,
        keys_to_apply=keys_present,
    )
    point.update(normalized)


def format_target_mapping_parts(row: Mapping[str, Any]) -> list[str]:
    """Compact target-mapping fragments for review/key lines."""
    parts: list[str] = []
    target_atom_id = row.get("target_atom_id")
    if isinstance(target_atom_id, str) and target_atom_id.strip():
        parts.append(f"target={target_atom_id.strip()}")
    target_context_id = row.get("target_context_id")
    if isinstance(target_context_id, str) and target_context_id.strip():
        parts.append(f"context={target_context_id.strip()}")
    hint = row.get("target_hint")
    if isinstance(hint, str) and hint.strip():
        parts.append(f'hint="{_escape_hint(hint.strip())}"')
    role = row.get("target_hint_role")
    if isinstance(role, str) and role.strip() and role.strip() != DEFAULT_TARGET_HINT_ROLE:
        parts.append(f"hint_role={role.strip()}")
    return parts


def _normalize_id(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()[:MAX_TARGET_ID_CHARS]
    if not text:
        _raise_param_error(f"{field} must be a non-empty bounded string when provided.")
    return text


def _normalize_hint(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > MAX_TARGET_HINT_CHARS:
        text = text[: MAX_TARGET_HINT_CHARS - 3] + "..."
    if "\n" in text or "\r" in text:
        _raise_param_error(f"{field} must be plain single-line text.")
    return text


def _normalize_hint_role(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    role = str(value).strip()
    if not role:
        return None
    if role not in ALLOWED_TARGET_HINT_ROLES:
        _raise_param_error(
            f"{field} must be one of: {sorted(ALLOWED_TARGET_HINT_ROLES)}.",
        )
    return role


def _raise_param_error(message: str) -> None:
    from .point_crops import PointCropParamError

    raise PointCropParamError(message)


def _escape_hint(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')
