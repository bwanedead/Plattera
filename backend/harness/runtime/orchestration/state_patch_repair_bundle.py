"""Compact carry-forward bundle for rejected/skipped state_patch rows.

Preserves agent-authored patch fragments and validation feedback so the next
turn can repair integration without redoing evidence. Mechanical only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = 1
REASON_ROWS_SKIPPED = "state_patch_rows_skipped"
REPAIR_INSTRUCTION = (
    "Repair the rejected patch shape/content directly. "
    "Do not redo evidence unless the evidence itself is missing or unusable."
)
PROMPT_INSTRUCTION = (
    "Prior state_patch integration failed or skipped rows. "
    "Repair the rejected patch directly before redoing evidence. "
    "The rejected fragments below may contain determinations/evidence that were not persisted."
)

MAX_FRAGMENTS = 5
MAX_VALIDATION_ERRORS_PER_FRAGMENT = 5
MAX_FRAGMENT_SERIALIZED_CHARS = 1500
MAX_TOTAL_BUNDLE_CHARS = 6000
MAX_PATH_CHARS = 400

_STRIP_FRAGMENT_KEYS = frozenset(
    {
        "b64",
        "bytes",
        "raw_image",
        "raw_image_data",
        "image_bytes",
        "raw_prompt_text",
        "raw_llm_response_text",
        "prompt_text",
    }
)
_PRESERVE_FRAGMENT_KEYS = frozenset(
    {
        "item_id",
        "unit_id",
        "status",
        "determination",
        "determined_value",
        "evidence_refs",
        "evidence_locators",
        "verification_basis",
        "closure_summary",
        "reopen_triggers",
        "summary",
        "title",
        "kind",
        "candidate_values",
        "label",
        "value_kind",
        "next_needed_step",
        "completion_criteria",
        "notes",
        "blocking",
        "requires_hitl",
        "no_further_progress",
        "structure_kind",
        "materiality",
    }
)

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
    projected["prompt_instruction"] = PROMPT_INSTRUCTION
    return _bound_total_bundle(projected)


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

    sanitized, truncated = _sanitize_fragment(fragment)
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
    sanitized, truncated = _sanitize_fragment(fragment)
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


def _sanitize_fragment(fragment: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    truncated = False
    out: dict[str, Any] = {}
    for key, value in fragment.items():
        key_text = str(key)
        if key_text in _STRIP_FRAGMENT_KEYS or key_text.endswith("_b64"):
            truncated = True
            continue
        if isinstance(value, (bytes, bytearray)):
            truncated = True
            continue
        if isinstance(value, str) and len(value) > 800:
            out[key_text] = value[:800]
            truncated = True
            continue
        if isinstance(value, list) and key_text in {"evidence_locators", "history", "context_notes"}:
            out[key_text] = _sanitize_nested_list(value)
            continue
        if isinstance(value, Mapping):
            nested, nested_truncated = _sanitize_fragment(value)
            if nested:
                out[key_text] = nested
            if nested_truncated:
                truncated = True
            continue
        out[key_text] = value

    # Prefer useful repair keys; drop unknown heavy keys if fragment is large.
    if len(json.dumps(out, ensure_ascii=False, default=str)) > MAX_FRAGMENT_SERIALIZED_CHARS:
        trimmed: dict[str, Any] = {}
        for key in _PRESERVE_FRAGMENT_KEYS:
            if key in out:
                trimmed[key] = out[key]
        if not trimmed:
            trimmed = {k: out[k] for k in list(out.keys())[:12]}
        out = trimmed
        truncated = True

    serialized = json.dumps(out, ensure_ascii=False, default=str)
    if len(serialized) > MAX_FRAGMENT_SERIALIZED_CHARS:
        out = _truncate_mapping_values(out, max_chars=MAX_FRAGMENT_SERIALIZED_CHARS)
        truncated = True
    return out, truncated


def _sanitize_nested_list(value: list[Any]) -> list[Any]:
    cleaned: list[Any] = []
    for row in value[:8]:
        if isinstance(row, Mapping):
            nested, _ = _sanitize_fragment(row)
            cleaned.append(nested)
        elif isinstance(row, str):
            cleaned.append(row[:400])
        else:
            cleaned.append(row)
    return cleaned


def _truncate_mapping_values(payload: Mapping[str, Any], *, max_chars: int) -> dict[str, Any]:
    out = dict(payload)
    while out and len(json.dumps(out, ensure_ascii=False, default=str)) > max_chars:
        longest_key = max(
            out.keys(),
            key=lambda k: len(json.dumps(out[k], ensure_ascii=False, default=str)),
        )
        current = out[longest_key]
        if isinstance(current, str) and len(current) > 80:
            out[longest_key] = current[: max(40, len(current) // 2)]
        else:
            del out[longest_key]
    return out


def _bound_fragments(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return fragments[:MAX_FRAGMENTS]


def _bound_total_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(bundle)
    while payload.get("fragments") and len(json.dumps(payload, ensure_ascii=False, default=str)) > MAX_TOTAL_BUNDLE_CHARS:
        frags = list(payload.get("fragments") or [])
        if len(frags) <= 1:
            payload["truncated"] = True
            payload["fragments"] = [_shrink_last_fragment(frags[0])] if frags else []
            break
        frags.pop()
        payload["fragments"] = frags
        payload["truncated"] = True
    return payload


def _shrink_last_fragment(fragment_row: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(fragment_row)
    fragment = row.get("fragment")
    if isinstance(fragment, Mapping):
        shrunk, truncated = _sanitize_fragment(fragment)
        row["fragment"] = _truncate_mapping_values(shrunk, max_chars=600)
        if truncated:
            row["truncated"] = True
    return row
