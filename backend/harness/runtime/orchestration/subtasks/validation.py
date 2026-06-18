"""Mechanical validation for parent-authored ``delegate_subtask`` inputs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .contracts import (
    DEFAULT_MAX_OUTPUT_CONTRACT_JSON_CHARS,
    MAX_CONTEXT_REF_CHARS,
    MAX_PROFILE_ID_CHARS,
    MAX_TARGET_ENTITY_ID_CHARS,
    DelegateSubtaskRequest,
    SubtaskProfile,
)
from .errors import SubtaskRegistryError, SubtaskValidationError
from .registry import DEFAULT_SUBTASK_REGISTRY, SubtaskProfileRegistry

_ALLOWED_KEYS = frozenset({
    "profile",
    "task",
    "context_refs",
    "target_entity_id",
    "isolation",
    "output_contract",
})
_PRIVATE_KEYS = frozenset({"_subtask_alias"})
_KNOWN_ISOLATION_FLAGS = frozenset({
    "omit_parent_graph",
    "omit_peer_candidates",
    "omit_parent_closure_ledger",
    "omit_broad_doctrine",
})


def validate_delegate_subtask_inputs(
    raw: Mapping[str, Any],
    *,
    registry: SubtaskProfileRegistry = DEFAULT_SUBTASK_REGISTRY,
    allow_private_keys: bool = False,
) -> DelegateSubtaskRequest:
    """Validate and normalize a parent-authored delegated subtask request."""

    if not isinstance(raw, Mapping):
        raise SubtaskValidationError("invalid_subtask_inputs", "delegate_subtask action_inputs must be an object")

    keys = set(raw.keys())
    allowed = set(_ALLOWED_KEYS)
    if allow_private_keys:
        allowed.update(_PRIVATE_KEYS)
    unknown = sorted(str(key) for key in keys - allowed)
    if unknown:
        raise SubtaskValidationError(
            "unknown_subtask_input_key",
            f"delegate_subtask action_inputs contained unknown keys: {', '.join(unknown)}",
        )

    profile_id = _required_text(raw.get("profile"), "profile", max_chars=MAX_PROFILE_ID_CHARS)
    try:
        profile = registry.require(profile_id)
    except SubtaskRegistryError as exc:
        raise SubtaskValidationError("unknown_subtask_profile", str(exc)) from exc

    task = _required_text(raw.get("task"), "task", max_chars=profile.max_task_chars)
    refs = _context_refs(raw.get("context_refs"), profile=profile)
    target_entity_id = _optional_text(
        raw.get("target_entity_id"),
        "target_entity_id",
        max_chars=MAX_TARGET_ENTITY_ID_CHARS,
    )
    isolation = _isolation(raw.get("isolation"))
    output_contract = _output_contract(raw.get("output_contract"))

    return DelegateSubtaskRequest(
        profile=profile.profile_id,
        task=task,
        context_refs=tuple(refs),
        target_entity_id=target_entity_id,
        isolation=isolation,
        output_contract=output_contract,
    )


def ref_kind(ref_id: str) -> str:
    """Return the generic ref kind used for profile allowlists."""

    text = str(ref_id or "").strip()
    if text.startswith("artifact://") or text.startswith("artifact:"):
        return "artifact"
    if text.startswith("image:"):
        return "image"
    if text.startswith("text:"):
        return "text"
    if ":" in text:
        return text.split(":", 1)[0].strip() or "unknown"
    return "unknown"


def _required_text(value: Any, field_name: str, *, max_chars: int) -> str:
    if not isinstance(value, str):
        raise SubtaskValidationError(
            f"{field_name}_required",
            f"delegate_subtask.{field_name} is required and must be a string",
        )
    text = value.strip()
    if not text:
        raise SubtaskValidationError(
            f"{field_name}_required",
            f"delegate_subtask.{field_name} is required and must be non-empty",
        )
    if len(text) > int(max_chars):
        raise SubtaskValidationError(
            f"{field_name}_too_long",
            f"delegate_subtask.{field_name} exceeds max length {int(max_chars)}",
        )
    return text


def _optional_text(value: Any, field_name: str, *, max_chars: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SubtaskValidationError(
            f"{field_name}_invalid",
            f"delegate_subtask.{field_name} must be a string when present",
        )
    text = value.strip()
    if not text:
        return None
    if len(text) > int(max_chars):
        raise SubtaskValidationError(
            f"{field_name}_too_long",
            f"delegate_subtask.{field_name} exceeds max length {int(max_chars)}",
        )
    return text


def _context_refs(raw: Any, *, profile: SubtaskProfile) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        raise SubtaskValidationError(
            "context_refs_required",
            "delegate_subtask.context_refs is required and must be a non-empty array",
        )
    if len(raw) < 1:
        raise SubtaskValidationError("context_refs_empty", "delegate_subtask.context_refs must be non-empty")
    cap = max(1, int(profile.max_context_refs))
    if len(raw) > cap:
        raise SubtaskValidationError(
            "context_refs_too_many",
            f"delegate_subtask.context_refs exceeds profile cap {cap}",
        )
    out: list[str] = []
    allowed = set(profile.allowed_ref_kinds)
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise SubtaskValidationError(
                "context_ref_invalid",
                f"delegate_subtask.context_refs[{index}] must be a non-empty string",
            )
        ref_id = item.strip()
        if len(ref_id) > MAX_CONTEXT_REF_CHARS:
            raise SubtaskValidationError(
                "context_ref_too_long",
                f"delegate_subtask.context_refs[{index}] exceeds max length {MAX_CONTEXT_REF_CHARS}",
            )
        kind = ref_kind(ref_id)
        if kind not in allowed:
            raise SubtaskValidationError(
                "context_ref_kind_disallowed",
                f"profile {profile.profile_id} does not allow ref kind {kind}",
            )
        out.append(ref_id)
    return out


def _isolation(raw: Any) -> dict[str, bool]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise SubtaskValidationError("isolation_invalid", "delegate_subtask.isolation must be an object")
    out: dict[str, bool] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if name not in _KNOWN_ISOLATION_FLAGS:
            raise SubtaskValidationError(
                "isolation_unknown_flag",
                f"delegate_subtask.isolation contains unknown flag: {name}",
            )
        out[name] = _boolish(value, field_name=f"isolation.{name}")
    return out


def _boolish(value: Any, *, field_name: str) -> bool:
    if type(value) is bool:
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    raise SubtaskValidationError(
        "isolation_flag_invalid",
        f"delegate_subtask.{field_name} must be boolean-ish",
    )


def _output_contract(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise SubtaskValidationError("output_contract_invalid", "delegate_subtask.output_contract must be an object")
    out = dict(raw)
    if _contains_key(out, "confidence"):
        raise SubtaskValidationError(
            "output_contract_confidence_disallowed",
            "delegate_subtask.output_contract must not request confidence fields",
        )
    try:
        size = len(json.dumps(out, separators=(",", ":"), default=str))
    except (TypeError, ValueError) as exc:
        raise SubtaskValidationError(
            "output_contract_invalid",
            "delegate_subtask.output_contract must be JSON-serializable",
        ) from exc
    if size > DEFAULT_MAX_OUTPUT_CONTRACT_JSON_CHARS:
        raise SubtaskValidationError(
            "output_contract_too_large",
            f"delegate_subtask.output_contract exceeds JSON size cap {DEFAULT_MAX_OUTPUT_CONTRACT_JSON_CHARS}",
        )
    return out


def _contains_key(value: Any, target: str) -> bool:
    if isinstance(value, Mapping):
        for key, inner in value.items():
            if str(key).strip().lower() == target:
                return True
            if _contains_key(inner, target):
                return True
    if isinstance(value, (list, tuple)):
        return any(_contains_key(item, target) for item in value)
    return False
