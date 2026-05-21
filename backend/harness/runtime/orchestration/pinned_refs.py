"""Mechanical pinned-ref attention for orchestration continuity.

Agents may pin a small bounded set of artifact refs to keep them hot across turns.
This module validates pin/unpin requests, mutates stored rows, and builds prompt
projections. It does not interpret artifact content or decide semantic readiness.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .hydrate_next import MAX_HYDRATE_NEXT_REF_CHARS

MAX_PINNED_REFS = 5
MAX_PIN_UNPIN_LIST_REFS = MAX_PINNED_REFS
MAX_EXPIRED_PIN_TAIL = MAX_PINNED_REFS
DEFAULT_PIN_TTL_TURNS = 8


class PinnedRefsValidationError(ValueError):
    """Raised when pin/unpin payloads fail mechanical validation."""


def normalize_pin_ref_list(raw: Any, *, field_name: str) -> tuple[str, ...]:
    """Validate optional pin/unpin arrays (same bounds style as hydrate_next)."""
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise PinnedRefsValidationError(f"{field_name} must be a JSON array of strings")
    cleaned: list[str] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, str):
            raise PinnedRefsValidationError(f"{field_name} entry at index {index} must be a string")
        text = entry.strip()
        if not text:
            raise PinnedRefsValidationError(f"{field_name} entry at index {index} must be non-empty")
        if len(text) > MAX_HYDRATE_NEXT_REF_CHARS:
            raise PinnedRefsValidationError(
                f"{field_name} entry at index {index} exceeds {MAX_HYDRATE_NEXT_REF_CHARS} chars"
            )
        if text not in cleaned:
            cleaned.append(text)
    if len(cleaned) > MAX_PIN_UNPIN_LIST_REFS:
        raise PinnedRefsValidationError(
            f"{field_name} exceeds max length {MAX_PIN_UNPIN_LIST_REFS}"
        )
    return tuple(cleaned)


def validate_stored_pinned_ref_row(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    ref = str(raw.get("ref") or "").strip()
    if not ref:
        return None
    try:
        pinned_at = int(raw.get("pinned_at_turn"))
        last_refreshed = int(raw.get("last_refreshed_turn"))
        ttl_turns = int(raw.get("ttl_turns"))
    except (TypeError, ValueError):
        return None
    if pinned_at < 0 or last_refreshed < 0 or ttl_turns < 1:
        return None
    return {
        "ref": ref,
        "pinned_at_turn": pinned_at,
        "last_refreshed_turn": last_refreshed,
        "ttl_turns": ttl_turns,
    }


def pin_is_active(row: Mapping[str, Any], *, current_turn: int) -> bool:
    last = int(row.get("last_refreshed_turn") or 0)
    ttl = int(row.get("ttl_turns") or DEFAULT_PIN_TTL_TURNS)
    return int(current_turn) <= last + ttl


def active_pinned_rows(
    rows: list[dict[str, Any]] | None,
    *,
    current_turn: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in list(rows or []):
        norm = validate_stored_pinned_ref_row(raw)
        if norm is None:
            continue
        if pin_is_active(norm, current_turn=current_turn):
            out.append(norm)
    return out[:MAX_PINNED_REFS]


def expired_pinned_rows(
    rows: list[dict[str, Any]] | None,
    *,
    current_turn: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in list(rows or []):
        norm = validate_stored_pinned_ref_row(raw)
        if norm is None:
            continue
        if not pin_is_active(norm, current_turn=current_turn):
            out.append(norm)
    return out


def apply_pin_updates(
    rows: list[dict[str, Any]] | None,
    *,
    pin_refs: tuple[str, ...],
    unpin_refs: tuple[str, ...],
    current_turn: int,
    ttl_turns: int = DEFAULT_PIN_TTL_TURNS,
) -> list[dict[str, Any]]:
    """Return updated pin rows after pin/unpin mutations (cap active pins)."""
    by_ref: dict[str, dict[str, Any]] = {}
    for raw in list(rows or []):
        norm = validate_stored_pinned_ref_row(raw)
        if norm is None:
            continue
        by_ref[norm["ref"]] = norm

    for ref in unpin_refs:
        by_ref.pop(ref, None)

    for ref in pin_refs:
        existing = by_ref.get(ref)
        if existing is not None:
            by_ref[ref] = {
                **existing,
                "last_refreshed_turn": int(current_turn),
                "ttl_turns": int(ttl_turns),
            }
        else:
            by_ref[ref] = {
                "ref": ref,
                "pinned_at_turn": int(current_turn),
                "last_refreshed_turn": int(current_turn),
                "ttl_turns": int(ttl_turns),
            }

    active = [
        row
        for row in by_ref.values()
        if pin_is_active(row, current_turn=current_turn)
    ]
    active.sort(key=lambda row: (int(row["last_refreshed_turn"]), row["ref"]))
    if len(active) > MAX_PINNED_REFS:
        for row in active[: len(active) - MAX_PINNED_REFS]:
            by_ref.pop(row["ref"], None)

    active_rows = [
        row
        for row in by_ref.values()
        if pin_is_active(row, current_turn=current_turn)
    ]
    expired_rows = [
        row
        for row in by_ref.values()
        if not pin_is_active(row, current_turn=current_turn)
    ]
    expired_rows.sort(
        key=lambda row: (-int(row["last_refreshed_turn"]), row["ref"]),
    )
    expired_tail = expired_rows[:MAX_EXPIRED_PIN_TAIL]
    kept_refs = {row["ref"] for row in active_rows} | {row["ref"] for row in expired_tail}
    return [
        row
        for row in sorted(
            (by_ref[ref] for ref in kept_refs if ref in by_ref),
            key=lambda item: (int(item["pinned_at_turn"]), item["ref"]),
        )
    ]


def build_pinned_refs_projection(
    rows: list[dict[str, Any]] | None,
    *,
    current_turn: int,
) -> dict[str, Any]:
    active = active_pinned_rows(rows, current_turn=current_turn)
    expired = expired_pinned_rows(rows, current_turn=current_turn)
    payload: dict[str, Any] = {
        "active": [
            {
                "ref": row["ref"],
                "pinned_at_turn": row["pinned_at_turn"],
                "last_refreshed_turn": row["last_refreshed_turn"],
                "ttl_turns": row["ttl_turns"],
            }
            for row in active
        ],
    }
    if expired:
        payload["expired"] = [
            {
                "ref": row["ref"],
                "pinned_at_turn": row["pinned_at_turn"],
                "last_refreshed_turn": row["last_refreshed_turn"],
            }
            for row in expired[:MAX_PINNED_REFS]
        ]
    return payload
