"""Compact carry-forward bundle for rejected/skipped state_patch rows.

Preserves agent-authored patch fragments and validation feedback so the next
turn can repair integration without redoing evidence. Mechanical only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .state_patch_repair_sanitization import (
    json_chars,
    sanitize_fragment,
    truncate_mapping_values,
)

SCHEMA_VERSION = 1
REASON_ROWS_SKIPPED = "state_patch_rows_skipped"
REASON_TERMINAL_ROW_LIVE_WORK = "terminal_row_live_work_conflict"
REPAIR_INSTRUCTION = (
    "Repair the rejected patch shape/content directly. "
    "Do not redo evidence unless the evidence itself is missing or unusable."
)
TERMINAL_ROW_REPAIR_INSTRUCTION = (
    "The fragments below were authored by the agent but were not persisted. "
    "Resolution item and covered-unit patches are sparse per-field overlays. "
    "Omitting a field preserves its existing value. "
    "To clear next_needed_step, send it explicitly as null. "
    "To clear requires_hitl or no_further_progress, send false. "
    "If closure remains honestly earned, merge required_clear_delta into that fragment "
    "and resubmit it. "
    "If work remains, do not apply the clear delta merely to satisfy the validator; "
    "author a nonterminal/reopened posture and retain an honest next step. "
    "The harness does not apply the fragment or clear delta automatically."
)
PROMPT_INSTRUCTION = (
    "Prior state_patch integration failed or skipped rows. "
    "Repair the rejected patch directly before redoing evidence. "
    "The rejected fragments below may contain determinations/evidence that were not persisted."
)
_CLEAR_DELTA_BY_FIELD = {
    "next_needed_step": None,
    "requires_hitl": False,
    "no_further_progress": False,
}

MAX_FRAGMENTS = 5
MAX_VALIDATION_ERRORS_PER_FRAGMENT = 5
MAX_TOTAL_BUNDLE_CHARS = 6000
MAX_PATH_CHARS = 400

_COVERED_UNIT_PATH_RE = re.compile(
    r"\.covered_units\[([^\]]+)\]|\.covered_units\[(\d+)\]"
)


def build_state_patch_repair_bundle(
    *,
    state_patch: Mapping[str, Any] | None,
    row_skip_details: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Build a bounded repair bundle from skipped rows and the original patch."""
    if not isinstance(state_patch, Mapping) or not isinstance(row_skip_details, Mapping):
        return None

    fragments: list[dict[str, Any]] = []
    resolution = row_skip_details.get("resolution")
    if isinstance(resolution, Mapping):
        for branch, predicate in (
            ("items", _fragment_from_item_skip),
            ("relations", _fragment_from_relation_skip),
        ):
            rows = resolution.get(branch)
            if not isinstance(rows, list):
                continue
            for detail in rows:
                if not isinstance(detail, Mapping):
                    continue
                fragment_row = predicate(state_patch, detail)
                if fragment_row is None:
                    continue
                fragments.append(fragment_row)
                if len(fragments) >= MAX_FRAGMENTS:
                    break
            if len(fragments) >= MAX_FRAGMENTS:
                break

    if not fragments:
        return None

    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "reason": REASON_ROWS_SKIPPED,
        "instruction": REPAIR_INSTRUCTION,
        "fragments": _bound_fragments(fragments),
    }
    bundle = _bound_total_bundle(bundle)
    return bundle


def build_terminal_row_consistency_repair_bundle(
    *,
    state_patch: Mapping[str, Any],
    result: Any,
) -> dict[str, Any] | None:
    """Build a bounded repair bundle for terminal-row / live-work conflicts.

    ``result`` is a ``TerminalRowConsistencyResult`` (or compatible mapping-like
    object with ``conflicts`` and ``conflicts_omitted_count``). Mechanical only:
    carries agent-authored fragments and clear-syntax deltas; does not apply them.
    """
    if not isinstance(state_patch, Mapping):
        return None
    conflicts = getattr(result, "conflicts", None)
    if not isinstance(conflicts, (list, tuple)) or not conflicts:
        return None
    omitted_base = int(getattr(result, "conflicts_omitted_count", 0) or 0)

    fragments: list[dict[str, Any]] = []
    for conflict in conflicts:
        fragment_row = _fragment_from_terminal_conflict(state_patch, conflict)
        if fragment_row is None:
            continue
        fragments.append(fragment_row)
        if len(fragments) >= MAX_FRAGMENTS:
            break

    if not fragments:
        return None

    retained = len(fragments)
    capacity_omitted = max(0, len(conflicts) - retained) + omitted_base
    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "reason": REASON_TERMINAL_ROW_LIVE_WORK,
        "instruction": TERMINAL_ROW_REPAIR_INSTRUCTION,
        "fragments": _bound_fragments(fragments),
    }
    if capacity_omitted:
        bundle["conflicts_omitted_count"] = capacity_omitted
    return _bound_total_bundle(bundle)


def project_state_patch_repair_bundle_for_prompt(
    feedback: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return prompt-visible repair bundle with carry-forward instruction."""
    if not isinstance(feedback, Mapping):
        return None
    bundle = feedback.get("state_patch_repair_bundle")
    if not isinstance(bundle, Mapping) or not bundle.get("fragments"):
        return None
    projected = dict(bundle)
    # Terminal-row bundles already carry their own instruction; do not overlay
    # the skip-row prompt_instruction as a competing authority.
    if str(projected.get("reason") or "").strip() != REASON_TERMINAL_ROW_LIVE_WORK:
        projected["prompt_instruction"] = PROMPT_INSTRUCTION
    return _bound_total_bundle(projected)


def required_clear_delta_for_fields(fields: Any) -> dict[str, Any]:
    """Return mechanical clear syntax for the named live-work fields only."""
    if not isinstance(fields, (list, tuple)):
        return {}
    delta: dict[str, Any] = {}
    for name in fields:
        key = str(name or "").strip()
        if key in _CLEAR_DELTA_BY_FIELD:
            delta[key] = _CLEAR_DELTA_BY_FIELD[key]
    # Preserve JSON-null clears through the same sanitizer used for fragments.
    sanitized, _ = sanitize_fragment(delta)
    return sanitized


def _fragment_from_terminal_conflict(
    state_patch: Mapping[str, Any],
    conflict: Any,
) -> dict[str, Any] | None:
    if isinstance(conflict, Mapping):
        coordinate = str(conflict.get("coordinate") or "").strip()
        fields_raw = conflict.get("fields") or ()
    else:
        coordinate = str(getattr(conflict, "coordinate", "") or "").strip()
        fields_raw = getattr(conflict, "fields", ()) or ()
    fields = tuple(str(f).strip() for f in fields_raw if str(f).strip())
    if not coordinate or not fields:
        return None

    item_id, unit_id = _parse_resolution_coordinate(coordinate)
    fragment: dict[str, Any] | None = None
    if item_id:
        patch_item = _find_patch_item(state_patch, item_id)
        if patch_item is not None and unit_id:
            patch_unit = _find_patch_unit(patch_item, unit_id)
            if patch_unit is not None:
                fragment = dict(patch_unit)
        elif patch_item is not None:
            # Parent-item conflict: carry item-own fields without nested units noise.
            fragment = {
                key: value
                for key, value in patch_item.items()
                if key != "covered_units"
            }

    if fragment is None:
        fragment = {}

    sanitized, truncated = sanitize_fragment(fragment)
    clear_delta = required_clear_delta_for_fields(fields)
    row: dict[str, Any] = {
        "path": coordinate[:MAX_PATH_CHARS],
        "reason_code": REASON_TERMINAL_ROW_LIVE_WORK,
        "conflicting_fields": list(fields),
        "fragment": sanitized,
        "required_clear_delta": clear_delta,
        "validation_errors": [
            f"contradictory live-work fields after sparse merge: {', '.join(fields)}"
        ][:MAX_VALIDATION_ERRORS_PER_FRAGMENT],
    }
    if truncated:
        row["truncated"] = True
    return row


def _parse_resolution_coordinate(coordinate: str) -> tuple[str, str | None]:
    """Return (item_id, unit_id_or_none) for a resolution coordinate path."""
    item_id = _bracket_id(coordinate, prefix="resolution.items[")
    if not item_id:
        return "", None
    unit_match = _COVERED_UNIT_PATH_RE.search(coordinate)
    if not unit_match:
        return item_id, None
    unit_id = (unit_match.group(1) or unit_match.group(2) or "").strip()
    return item_id, unit_id or None


def _fragment_from_item_skip(
    state_patch: Mapping[str, Any],
    detail: Mapping[str, Any],
) -> dict[str, Any] | None:
    path = str(detail.get("path") or "").strip()
    reason_code = str(detail.get("reason_code") or "validation_failed").strip()
    validation_errors = _normalize_validation_errors(detail.get("validation_errors"))
    row_id = str(detail.get("row_id") or "").strip()

    item_id = row_id
    if not item_id and path.startswith("resolution.items["):
        item_id = _bracket_id(path, prefix="resolution.items[")

    patch_item = _find_patch_item(state_patch, item_id) if item_id else None
    unit_id = _unit_id_from_detail(path, validation_errors)
    fragment_path = path
    fragment: dict[str, Any] | None = None

    if unit_id and patch_item is not None:
        patch_unit = _find_patch_unit(patch_item, unit_id)
        if patch_unit is not None:
            fragment = dict(patch_unit)
            if item_id:
                fragment_path = f"resolution.items[{item_id}].covered_units[{unit_id}]"
    elif patch_item is not None:
        fragment = dict(patch_item)
        if item_id:
            fragment_path = f"resolution.items[{item_id}]"

    if fragment is None:
        if not patch_item and not validation_errors:
            return None
        fragment = dict(patch_item) if isinstance(patch_item, Mapping) else {}

    sanitized, truncated = sanitize_fragment(fragment)
    if not sanitized and not validation_errors:
        return None

    row: dict[str, Any] = {
        "path": fragment_path[:MAX_PATH_CHARS],
        "reason_code": reason_code,
        "validation_errors": validation_errors[:MAX_VALIDATION_ERRORS_PER_FRAGMENT],
        "fragment": sanitized,
    }
    if truncated:
        row["truncated"] = True
    return row


def _fragment_from_relation_skip(
    state_patch: Mapping[str, Any],
    detail: Mapping[str, Any],
) -> dict[str, Any] | None:
    path = str(detail.get("path") or "").strip()
    reason_code = str(detail.get("reason_code") or "validation_failed").strip()
    validation_errors = _normalize_validation_errors(detail.get("validation_errors"))
    index = _index_from_relation_path(path)
    patch_relation = _find_patch_relation(state_patch, index)
    if patch_relation is None and not validation_errors:
        return None
    fragment = dict(patch_relation) if isinstance(patch_relation, Mapping) else {}
    sanitized, truncated = sanitize_fragment(fragment)
    row: dict[str, Any] = {
        "path": path[:MAX_PATH_CHARS] or f"resolution.relations[{index if index is not None else '?'}]",
        "reason_code": reason_code,
        "validation_errors": validation_errors[:MAX_VALIDATION_ERRORS_PER_FRAGMENT],
        "fragment": sanitized,
    }
    if truncated:
        row["truncated"] = True
    return row


def _find_patch_item(state_patch: Mapping[str, Any], item_id: str) -> dict[str, Any] | None:
    resolution = state_patch.get("resolution")
    if not isinstance(resolution, Mapping):
        return None
    items = resolution.get("items")
    if isinstance(items, Mapping):
        return dict(items) if str(items.get("item_id") or "").strip() == item_id else None
    if not isinstance(items, list):
        return None
    for row in items:
        if isinstance(row, Mapping) and str(row.get("item_id") or "").strip() == item_id:
            return dict(row)
    return None


def _find_patch_unit(patch_item: Mapping[str, Any], unit_id: str) -> dict[str, Any] | None:
    units = patch_item.get("covered_units")
    if isinstance(units, Mapping):
        if str(units.get("unit_id") or "").strip() == unit_id:
            return dict(units)
        return None
    if not isinstance(units, list):
        return None
    for row in units:
        if isinstance(row, Mapping) and str(row.get("unit_id") or "").strip() == unit_id:
            return dict(row)
    return None


def _find_patch_relation(state_patch: Mapping[str, Any], index: int | None) -> dict[str, Any] | None:
    if index is None:
        return None
    resolution = state_patch.get("resolution")
    if not isinstance(resolution, Mapping):
        return None
    relations = resolution.get("relations")
    if isinstance(relations, Mapping):
        return dict(relations) if index == 0 else None
    if not isinstance(relations, list) or index < 0 or index >= len(relations):
        return None
    row = relations[index]
    return dict(row) if isinstance(row, Mapping) else None


def _unit_id_from_detail(path: str, validation_errors: list[str]) -> str:
    for source in (path, *validation_errors):
        match = _COVERED_UNIT_PATH_RE.search(str(source))
        if not match:
            continue
        unit_id = (match.group(1) or match.group(2) or "").strip()
        if unit_id:
            return unit_id
    return ""


def _bracket_id(path: str, *, prefix: str) -> str:
    if not path.startswith(prefix):
        return ""
    rest = path[len(prefix) :]
    end = rest.find("]")
    if end <= 0:
        return ""
    return rest[:end].strip()


def _index_from_relation_path(path: str) -> int | None:
    prefix = "resolution.relations["
    if not path.startswith(prefix):
        return None
    rest = path[len(prefix) :]
    end = rest.find("]")
    if end <= 0:
        return None
    try:
        return int(rest[:end])
    except ValueError:
        return None


def _normalize_validation_errors(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for row in raw:
        text = str(row or "").strip()
        if text:
            out.append(text[:400])
    return out


def _bound_fragments(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return fragments[:MAX_FRAGMENTS]


def _payload_over_budget(payload: Mapping[str, Any]) -> bool:
    try:
        return json_chars(payload) > MAX_TOTAL_BUNDLE_CHARS
    except (TypeError, ValueError):
        return True


def _set_terminal_omission_count(
    payload: dict[str, Any],
    *,
    initial_omitted: int,
    dropped: int,
) -> None:
    if str(payload.get("reason") or "").strip() != REASON_TERMINAL_ROW_LIVE_WORK:
        return
    total = initial_omitted + dropped
    if total > 0:
        payload["conflicts_omitted_count"] = total
    elif "conflicts_omitted_count" in payload:
        # Keep an explicit zero only when already present; otherwise omit.
        payload["conflicts_omitted_count"] = 0


def _bound_total_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Fit the bundle under ``MAX_TOTAL_BUNDLE_CHARS`` with an honest omission marker.

    For terminal-row bundles, ``conflicts_omitted_count`` is updated on each
    fragment drop so every subsequent fit measurement includes the final marker.
    After last-fragment shrinking, the strict compact JSON length is checked again.
    """
    payload = dict(bundle)
    is_terminal = str(payload.get("reason") or "").strip() == REASON_TERMINAL_ROW_LIVE_WORK
    initial_omitted = int(payload.get("conflicts_omitted_count") or 0) if is_terminal else 0
    dropped = 0

    while payload.get("fragments"):
        if not _payload_over_budget(payload):
            break
        frags = list(payload.get("fragments") or [])
        if len(frags) <= 1:
            payload["truncated"] = True
            payload["fragments"] = [_shrink_last_fragment(frags[0])] if frags else []
            # Omission marker (if any) already reflects prior drops; re-check size.
            if _payload_over_budget(payload) and payload.get("fragments"):
                payload["fragments"] = [
                    _shrink_last_fragment_hard(payload["fragments"][0])
                ]
            break
        frags.pop()
        dropped += 1
        payload["fragments"] = frags
        payload["truncated"] = True
        if is_terminal:
            _set_terminal_omission_count(
                payload,
                initial_omitted=initial_omitted,
                dropped=dropped,
            )

    return payload


def _shrink_last_fragment(fragment_row: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(fragment_row)
    fragment = row.get("fragment")
    if isinstance(fragment, Mapping):
        shrunk, truncated = sanitize_fragment(fragment)
        row["fragment"] = truncate_mapping_values(shrunk, max_chars=600)
        if truncated:
            row["truncated"] = True
    clear_delta = row.get("required_clear_delta")
    if isinstance(clear_delta, Mapping):
        sanitized_delta, _ = sanitize_fragment(clear_delta)
        row["required_clear_delta"] = sanitized_delta
    return row


def _shrink_last_fragment_hard(fragment_row: Mapping[str, Any]) -> dict[str, Any]:
    """Further shrink a sole remaining fragment when still over the total budget."""
    row = _shrink_last_fragment(fragment_row)
    fragment = row.get("fragment")
    if isinstance(fragment, Mapping):
        row["fragment"] = truncate_mapping_values(fragment, max_chars=200)
    # Drop non-essential diagnostic lists while retaining repair coordinates.
    row.pop("validation_errors", None)
    return row
