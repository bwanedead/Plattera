"""Mechanical helpers for agent-authored ``hydrate_next`` requests.

Generic harness infrastructure: validates and normalizes the optional
``hydrate_next`` / ``hydrate_next_reason`` fields the agent may attach to any
action plan, resolves ``@result.*`` placeholders against the just-executed
tool result, and builds the per-turn record the orchestrator persists into
continuity so the next turn can surface the hydrated refs in prompt context.

No semantic prioritization — this module never decides which refs matter.
It clamps, dedupes, validates, and records.  The canonical shared hydration
tool id (``hydrate_artifact_refs``) is referenced as a constant so the
orchestrator can re-dispatch a bounded hydration step on behalf of the agent
without authoring the next turn itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Canonical shared hydration tool id (see ``tooling/artifact_capability``).
# Held here as a string constant so harness core does not import from the
# tooling layer; the orchestrator dispatches by id through the session manager.
HYDRATE_ARTIFACT_REFS_ACTION_ID = "hydrate_artifact_refs"

MAX_HYDRATE_NEXT_REFS = 5
MAX_HYDRATE_NEXT_REF_CHARS = 256
MAX_HYDRATE_NEXT_REASON_CHARS = 400

# Supported placeholder forms.  Single-value placeholders resolve from the
# tool result's ``outputs`` mapping; the ``[]`` form pulls the bounded
# ``artifact_refs`` list off the result.
_SINGLE_PLACEHOLDERS: dict[str, str] = {
    "@result.derived_ref_id": "derived_ref_id",
    "@result.revision_ref": "revision_ref",
    "@result.published_ref": "published_ref",
}
_LIST_PLACEHOLDER = "@result.artifact_refs[]"
_BATCH_LIST_SUFFIX = ".result.artifact_refs[]"
_BATCH_SINGLE_SUFFIXES: dict[str, str] = {
    ".result.derived_ref_id": "derived_ref_id",
    ".result.revision_ref": "revision_ref",
    ".result.published_ref": "published_ref",
}


class HydrateNextValidationError(ValueError):
    """Raised by ``normalize_hydrate_next`` / reason validators on shape failure."""


def normalize_hydrate_next(raw: Any) -> tuple[list[str], list[dict[str, Any]]]:
    """Return ``(requested_refs, parse_errors)``.

    ``raw`` may be ``None`` (no request), a list of strings (each entry is a
    literal ref or supported placeholder).  Non-list inputs raise; non-string
    entries are surfaced as parse errors (the action plan parser converts these
    into a repairable validation failure).  The list is clamped to
    ``MAX_HYDRATE_NEXT_REFS`` after dedupe-preserving-order.
    """
    if raw is None:
        return [], []
    if not isinstance(raw, (list, tuple)):
        raise HydrateNextValidationError("hydrate_next must be a JSON array of strings")

    errors: list[dict[str, Any]] = []
    cleaned: list[str] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, str):
            errors.append({
                "requested_ref": None,
                "reason_code": "non_string_entry",
                "index": index,
            })
            continue
        text = entry.strip()
        if not text:
            errors.append({
                "requested_ref": "",
                "reason_code": "blank_entry",
                "index": index,
            })
            continue
        if len(text) > MAX_HYDRATE_NEXT_REF_CHARS:
            # Refs are identifiers — truncating would silently change the
            # requested target.  Reject as a repairable validation error so
            # the agent fixes it rather than seeing a confusing "not found".
            raise HydrateNextValidationError(
                f"hydrate_next entry at index {index} exceeds "
                f"{MAX_HYDRATE_NEXT_REF_CHARS} chars"
            )
        if text not in cleaned:
            cleaned.append(text)

    if len(cleaned) > MAX_HYDRATE_NEXT_REFS:
        raise HydrateNextValidationError(
            f"hydrate_next exceeds max length {MAX_HYDRATE_NEXT_REFS}"
        )
    return cleaned, errors


def normalize_hydrate_next_reason(raw: Any) -> str | None:
    """Return the cleaned reason string, or None if absent/blank.

    Raises on non-string, non-null inputs; clamps overlong text rather than
    rejecting it (the field is advisory).
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise HydrateNextValidationError(
            "hydrate_next_reason must be a string or null"
        )
    text = raw.strip()
    if not text:
        return None
    if len(text) > MAX_HYDRATE_NEXT_REASON_CHARS:
        text = text[:MAX_HYDRATE_NEXT_REASON_CHARS]
    return text


def _resolve_batch_placeholder(
    entry: str,
    *,
    batch_results: Mapping[str, Mapping[str, Any]] | None,
    resolved: list[str],
    errors: list[dict[str, Any]],
) -> None:
    if batch_results is None:
        errors.append({"requested_ref": entry, "reason_code": "batch_result_not_found"})
        return
    if entry.endswith(_BATCH_LIST_SUFFIX):
        alias = entry[len("@batch.") : -len(_BATCH_LIST_SUFFIX)]
        if not alias or "." in alias:
            errors.append({"requested_ref": entry, "reason_code": "unknown_placeholder"})
            return
        snap = batch_results.get(alias)
        if not snap:
            errors.append({"requested_ref": entry, "reason_code": "batch_alias_not_found"})
            return
        artifact_refs = snap.get("artifact_refs")
        if not isinstance(artifact_refs, (list, tuple)) or not artifact_refs:
            errors.append({"requested_ref": entry, "reason_code": "placeholder_not_found"})
            return
        for ref in artifact_refs:
            if len(resolved) >= MAX_HYDRATE_NEXT_REFS:
                break
            if isinstance(ref, str) and ref.strip() and ref.strip() not in resolved:
                resolved.append(ref.strip())
        return
    for suffix, outputs_key in _BATCH_SINGLE_SUFFIXES.items():
        if not entry.endswith(suffix):
            continue
        alias = entry[len("@batch.") : -len(suffix)]
        if not alias or "." in alias:
            errors.append({"requested_ref": entry, "reason_code": "unknown_placeholder"})
            return
        snap = batch_results.get(alias)
        if not snap:
            errors.append({"requested_ref": entry, "reason_code": "batch_alias_not_found"})
            return
        outputs = snap.get("outputs")
        outputs_map = outputs if isinstance(outputs, Mapping) else {}
        value = outputs_map.get(outputs_key)
        if not isinstance(value, str) or not value.strip():
            errors.append({"requested_ref": entry, "reason_code": "placeholder_not_found"})
            return
        if value.strip() not in resolved:
            resolved.append(value.strip())
        return
    errors.append({"requested_ref": entry, "reason_code": "unknown_placeholder"})


def resolve_hydrate_next_refs(
    requested: list[str] | tuple[str, ...],
    *,
    tool_result: Mapping[str, Any] | None,
    batch_results: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Resolve placeholders to concrete refs against the current tool result.

    ``tool_result`` is a small mapping with keys ``outputs`` (mapping) and
    ``artifact_refs`` (sequence of strings).  The orchestrator builds it from
    the just-completed ``ActionDispatchResult``.  Returns
    ``(resolved_refs, errors)`` where ``resolved_refs`` is deduped
    order-preserving and clamped to ``MAX_HYDRATE_NEXT_REFS``.  Each error row
    has ``{"requested_ref": str, "reason_code": str}``.
    """
    if tool_result is None:
        outputs: Mapping[str, Any] = {}
        artifact_refs: list[str] = []
    else:
        raw_outputs = tool_result.get("outputs")
        outputs = raw_outputs if isinstance(raw_outputs, Mapping) else {}
        raw_refs = tool_result.get("artifact_refs")
        if isinstance(raw_refs, (list, tuple)):
            artifact_refs = [str(x) for x in raw_refs if isinstance(x, str) and x.strip()]
        else:
            artifact_refs = []

    resolved: list[str] = []
    errors: list[dict[str, Any]] = []

    def _append(ref: str) -> None:
        if ref and ref not in resolved:
            resolved.append(ref)

    for entry in requested:
        if not isinstance(entry, str):
            errors.append({"requested_ref": str(entry), "reason_code": "non_string_entry"})
            continue
        if not entry.startswith("@"):
            _append(entry)
            continue
        if entry.startswith("@this."):
            entry = "@result." + entry[len("@this.") :]
        if entry.startswith("@batch."):
            _resolve_batch_placeholder(
                entry,
                batch_results=batch_results,
                resolved=resolved,
                errors=errors,
            )
            if len(resolved) >= MAX_HYDRATE_NEXT_REFS:
                break
            continue
        if entry == _LIST_PLACEHOLDER:
            if not artifact_refs:
                errors.append({
                    "requested_ref": entry,
                    "reason_code": "placeholder_not_found",
                })
                continue
            for ref in artifact_refs:
                if len(resolved) >= MAX_HYDRATE_NEXT_REFS:
                    break
                _append(ref)
            continue
        outputs_key = _SINGLE_PLACEHOLDERS.get(entry)
        if outputs_key is None:
            errors.append({
                "requested_ref": entry,
                "reason_code": "unknown_placeholder",
            })
            continue
        value = outputs.get(outputs_key) if isinstance(outputs, Mapping) else None
        if not isinstance(value, str) or not value.strip():
            errors.append({
                "requested_ref": entry,
                "reason_code": "placeholder_not_found",
            })
            continue
        _append(value.strip())
        if len(resolved) >= MAX_HYDRATE_NEXT_REFS:
            break

    if len(resolved) > MAX_HYDRATE_NEXT_REFS:
        resolved = resolved[:MAX_HYDRATE_NEXT_REFS]
    return resolved, errors


def build_hydrate_next_record(
    *,
    requested_refs: list[str] | tuple[str, ...],
    resolved_refs: list[str] | tuple[str, ...],
    reason: str | None,
    errors: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    source_turn_index: int,
) -> dict[str, Any]:
    """Build the canonical pending hydration record stored on continuity.

    Status starts at ``"pending"``; orchestrator flips to ``"surfaced"`` after
    the next-turn prompt has included the lane.  ``hydrated_results`` and
    ``hydration_errors`` are filled in later by the orchestrator after it
    dispatches the bounded hydration step.
    """
    return {
        "source_turn_index": int(source_turn_index),
        "requested_refs": [str(r) for r in requested_refs],
        "resolved_refs": [str(r) for r in resolved_refs],
        "reason": reason if isinstance(reason, str) and reason else None,
        "errors": [dict(e) for e in errors if isinstance(e, Mapping)],
        "hydrated_results": None,
        "hydration_errors": None,
        "status": "pending",
        "surfaced_iteration": None,
    }


def validate_stored_hydrate_next_record(row: Any) -> dict[str, Any] | None:
    """Resume-snapshot validator.  Returns the normalized record or ``None``.

    Old snapshots without this field will pass ``None``; resume code treats
    that as "no pending request."
    """
    if row is None or not isinstance(row, Mapping):
        return None
    try:
        source_turn_index = int(row.get("source_turn_index", 0))
    except (TypeError, ValueError):
        return None
    if source_turn_index < 0:
        return None

    requested_raw = row.get("requested_refs") or []
    if not isinstance(requested_raw, (list, tuple)):
        return None
    requested_refs = [str(x) for x in requested_raw if isinstance(x, str)]

    resolved_raw = row.get("resolved_refs") or []
    if not isinstance(resolved_raw, (list, tuple)):
        return None
    resolved_refs = [str(x) for x in resolved_raw if isinstance(x, str)]

    reason = row.get("reason")
    if reason is not None and not isinstance(reason, str):
        return None

    errors_raw = row.get("errors") or []
    if not isinstance(errors_raw, (list, tuple)):
        return None
    errors = [dict(e) for e in errors_raw if isinstance(e, Mapping)]

    hydrated_results = row.get("hydrated_results")
    if hydrated_results is not None and not isinstance(hydrated_results, (list, tuple)):
        return None
    if isinstance(hydrated_results, tuple):
        hydrated_results = list(hydrated_results)

    hydration_errors = row.get("hydration_errors")
    if hydration_errors is not None and not isinstance(hydration_errors, (list, tuple)):
        return None
    if isinstance(hydration_errors, tuple):
        hydration_errors = list(hydration_errors)

    status = str(row.get("status") or "pending").strip()
    if status not in {"pending", "surfaced"}:
        return None

    surfaced_iteration = row.get("surfaced_iteration")
    if surfaced_iteration is not None:
        try:
            surfaced_iteration = int(surfaced_iteration)
        except (TypeError, ValueError):
            return None

    return {
        "source_turn_index": source_turn_index,
        "requested_refs": requested_refs,
        "resolved_refs": resolved_refs,
        "reason": reason if reason else None,
        "errors": errors,
        "hydrated_results": list(hydrated_results) if hydrated_results is not None else None,
        "hydration_errors": list(hydration_errors) if hydration_errors is not None else None,
        "status": status,
        "surfaced_iteration": surfaced_iteration,
    }


def build_tool_result_snapshot(
    *,
    outputs: Mapping[str, Any] | None,
    artifact_refs: list[str] | tuple[str, ...] | None,
) -> dict[str, Any]:
    """Bounded snapshot of a tool result for placeholder resolution.

    Held as a tiny mapping so callers don't pass full ``ActionDispatchResult``
    objects into the resolver.  Only the keys the resolver consults are
    forwarded; everything else is dropped.
    """
    snapshot: dict[str, Any] = {}
    if isinstance(outputs, Mapping):
        snapshot["outputs"] = {k: outputs.get(k) for k in (
            "derived_ref_id", "revision_ref", "published_ref",
        ) if k in outputs}
    if isinstance(artifact_refs, (list, tuple)):
        snapshot["artifact_refs"] = [str(x) for x in artifact_refs if isinstance(x, str) and x.strip()]
    return snapshot
