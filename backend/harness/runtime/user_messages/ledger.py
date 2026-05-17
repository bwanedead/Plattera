"""Append-only user-message ledger — durable mechanical history of each
user-to-agent message injected into a run.

Each entry captures:
  - the exact inbound text and metadata (bounded at admission)
  - mechanical delivery iteration (when the loop first ingested the message)
  - mechanical consumption status (when the agent declares it integrated, or
    explicitly defers with a reason)

This module is intentionally generic — it does not encode any domain semantics.
Domains decide what "consuming" a message means (state changes, artifact
edits, scope changes, etc.).  The harness only delivers, accounts, and
projects the exact user-authored text.

Separate from the HITL exchange ledger: HITL is agent-initiated, user messages
are user-initiated, and conflating them would confuse the prompt-projection
contract and the consumption ledgers.
"""

from __future__ import annotations

import uuid as _uuid_mod
from collections.abc import Mapping
from typing import Any, Literal

from .message_shape import USER_MESSAGE_BOUND_KEYS, clamp_defer_reason, normalize_user_message

UserMessageStatus = Literal["pending", "consumed", "deferred"]

# Bounded compaction: drop only old consumed/deferred entries past the cap.
# Pending entries are never dropped — losing them would erase the very thing
# the channel exists to deliver.
_MAX_LEDGER_TOTAL = 256
_MAX_TERMINAL_RETAINED = 64

MESSAGE_ID_PREFIX = "user-msg-"


def make_message_id() -> str:
    """Generate a fresh user-message id with the harness convention prefix."""
    return f"{MESSAGE_ID_PREFIX}{_uuid_mod.uuid4().hex}"


def _find_index_by_message_id(ledger: list[dict[str, Any]], message_id: str) -> int:
    mid = str(message_id or "").strip()
    if not mid:
        return -1
    for idx, entry in enumerate(ledger):
        if str(entry.get("message_id") or "").strip() == mid:
            return idx
    return -1


def record_inbound(
    ledger: list[dict[str, Any]],
    *,
    message_id: str,
    text: str,
    created_at_epoch_seconds: int | float,
    iteration: int,
    source: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    bounds: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Append a new pending entry for an inbound user message.

    Idempotent on ``message_id``: if the same id is recorded twice (e.g. the
    poll cycle sees the same store entry twice across a resume), the existing
    entry is preserved unchanged — text and metadata are NOT overwritten so
    consumption status survives.

    Returns ``(new_ledger, newly_appended)``.  ``newly_appended`` is True
    only on first ingestion.
    """
    raw_mid = str(message_id or "").strip()
    if not raw_mid:
        return list(ledger), False
    id_shape = normalize_user_message({"message_id": raw_mid})
    mid = str(id_shape.get("message_id") or "").strip()
    if not mid:
        return list(ledger), False
    new_ledger = list(ledger)
    idx = _find_index_by_message_id(new_ledger, mid)
    if idx >= 0:
        return new_ledger, False

    raw = {
        "message_id": mid,
        "created_at_epoch_seconds": created_at_epoch_seconds,
        "source": source,
        "text": text,
        "metadata": dict(metadata) if isinstance(metadata, Mapping) else {},
    }
    preserved_bounds: dict[str, Any] = {}
    if isinstance(id_shape.get("_bounds"), Mapping):
        preserved_bounds.update(dict(id_shape["_bounds"]))
    if isinstance(bounds, Mapping):
        preserved_bounds.update(dict(bounds))
    if preserved_bounds:
        raw["_bounds"] = preserved_bounds
    normalized = normalize_user_message(raw)
    entry: dict[str, Any] = {
        "message_id": normalized.get("message_id") or mid,
        "created_at_epoch_seconds": normalized.get("created_at_epoch_seconds"),
        "source": normalized.get("source"),
        "text": normalized.get("text", ""),
        "metadata": normalized.get("metadata", {}),
        "status": "pending",
        "received_at_iteration": int(iteration),
        "consumed_iteration": None,
        "defer_reason": None,
        "deferred_iteration": None,
    }
    if "_bounds" in normalized:
        entry["_bounds"] = dict(normalized["_bounds"])
    new_ledger.append(entry)
    return clamp_ledger(new_ledger), True


def mark_consumed(
    ledger: list[dict[str, Any]],
    *,
    message_ids: tuple[str, ...] | list[str],
    iteration: int,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Mark matching entries as consumed; record consumed_iteration.

    Returns ``(new_ledger, matched_ids, unknown_ids)``.  An unknown id is one
    declared by the agent that has no matching ledger entry — used to surface
    integration drift without modifying the ledger.

    Idempotent on already-consumed entries.  An entry currently in ``deferred``
    state can still be consumed by a later turn (the defer was a "not yet",
    not a permanent rejection).
    """
    want = [str(x).strip() for x in (message_ids or ()) if str(x).strip()]
    if not want:
        return list(ledger), [], []
    new_ledger = list(ledger)
    matched: list[str] = []
    unknown: list[str] = []
    for mid in want:
        idx = _find_index_by_message_id(new_ledger, mid)
        if idx < 0:
            unknown.append(mid)
            continue
        existing = dict(new_ledger[idx])
        if existing.get("status") != "consumed":
            existing["status"] = "consumed"
            existing["consumed_iteration"] = int(iteration)
        matched.append(mid)
        new_ledger[idx] = existing
    return clamp_ledger(new_ledger), matched, unknown


def mark_deferred(
    ledger: list[dict[str, Any]],
    *,
    defers: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    iteration: int,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Mark matching entries as deferred with a short reason.

    Each defer entry is ``{"message_id": str, "reason": str}``.  Reason is
    bounded by ``clamp_defer_reason``.

    Returns ``(new_ledger, matched_ids, unknown_ids)``.  Idempotent in the
    sense that re-marking an already-deferred entry just updates the reason
    and iteration.
    """
    matched: list[str] = []
    unknown: list[str] = []
    if not defers:
        return list(ledger), matched, unknown
    new_ledger = list(ledger)
    for raw in defers:
        if not isinstance(raw, Mapping):
            continue
        mid = str(raw.get("message_id") or "").strip()
        if not mid:
            continue
        reason = clamp_defer_reason(raw.get("reason"))
        idx = _find_index_by_message_id(new_ledger, mid)
        if idx < 0:
            unknown.append(mid)
            continue
        existing = dict(new_ledger[idx])
        if existing.get("status") == "consumed":
            # Already terminal in the strong sense — don't downgrade.
            matched.append(mid)
            continue
        existing["status"] = "deferred"
        existing["defer_reason"] = reason
        existing["deferred_iteration"] = int(iteration)
        new_ledger[idx] = existing
        matched.append(mid)
    return clamp_ledger(new_ledger), matched, unknown


def clamp_ledger(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bounded compaction: drop oldest *terminal* (consumed or deferred)
    entries past the retention cap.  Pending entries are never dropped.
    """
    if len(ledger) <= _MAX_LEDGER_TOTAL:
        terminal = [e for e in ledger if e.get("status") in ("consumed", "deferred")]
        if len(terminal) <= _MAX_TERMINAL_RETAINED:
            return list(ledger)
        keep_ids = set(id(e) for e in terminal[-_MAX_TERMINAL_RETAINED:])
        return [
            e for e in ledger
            if e.get("status") not in ("consumed", "deferred") or id(e) in keep_ids
        ]
    pending = [e for e in ledger if e.get("status") == "pending"]
    terminal = [e for e in ledger if e.get("status") in ("consumed", "deferred")]
    terminal_keep = terminal[-_MAX_TERMINAL_RETAINED:]
    return pending + terminal_keep


def count_pending(ledger: list[dict[str, Any]]) -> int:
    return sum(1 for e in ledger if e.get("status") == "pending")


def count_consumed(ledger: list[dict[str, Any]]) -> int:
    return sum(1 for e in ledger if e.get("status") == "consumed")


def count_deferred(ledger: list[dict[str, Any]]) -> int:
    return sum(1 for e in ledger if e.get("status") == "deferred")


def get_message(ledger: list[dict[str, Any]], message_id: str) -> dict[str, Any] | None:
    idx = _find_index_by_message_id(ledger, message_id)
    if idx < 0:
        return None
    return dict(ledger[idx])


def render_user_message_audit_view(
    ledger: list[dict[str, Any]],
    *,
    max_entries: int = 64,
    text_max_chars: int = 400,
) -> list[dict[str, Any]]:
    """Projection-only audit view for human timeline rendering.

    Each entry is rendered to a compact, audit-friendly dict.  Read-only —
    consumers (UI, audit reports) treat this as a derived projection, not a
    source of truth.  Includes admission-time ``_bounds`` markers plus a
    distinct ``text_display_truncated`` marker when the audit clip kicks in.
    """
    rendered: list[dict[str, Any]] = []
    for entry in ledger[-max_entries:]:
        text = str(entry.get("text") or "")
        display_truncated = False
        if len(text) > text_max_chars:
            text = text[:text_max_chars] + "…"
            display_truncated = True
        view: dict[str, Any] = {
            "message_id": entry.get("message_id"),
            "created_at_epoch_seconds": entry.get("created_at_epoch_seconds"),
            "source": entry.get("source"),
            "status": entry.get("status"),
            "text": text,
            "metadata": dict(entry.get("metadata") or {}) if isinstance(entry.get("metadata"), Mapping) else {},
            "received_at_iteration": entry.get("received_at_iteration"),
            "consumed_iteration": entry.get("consumed_iteration"),
            "deferred_iteration": entry.get("deferred_iteration"),
            "defer_reason": entry.get("defer_reason"),
        }
        admission_bounds = entry.get("_bounds") if isinstance(entry.get("_bounds"), Mapping) else None
        if admission_bounds or display_truncated:
            merged_bounds: dict[str, bool] = {}
            if isinstance(admission_bounds, Mapping):
                for k, v in admission_bounds.items():
                    if k in USER_MESSAGE_BOUND_KEYS and v is True:
                        merged_bounds[str(k)] = True
            if display_truncated:
                merged_bounds["text_display_truncated"] = True
            view["_bounds"] = merged_bounds
        rendered.append(view)
    return rendered


def build_prompt_user_message_view(
    ledger: list[dict[str, Any]],
    *,
    max_total: int = 16,
    recent_terminal_keep: int = 3,
    text_max_chars: int = 1_200,
) -> list[dict[str, Any]]:
    """Bounded view for prompt projection.

    Inclusion policy (mechanical, no semantics):
    - ``pending`` entries win the bounded prompt slots so the agent can act.
    - Most recent ``recent_terminal_keep`` consumed-or-deferred entries (for
      audit/recency context) with full payloads.
    - Older terminal entries omitted.

    Total result is capped at ``max_total``; pending entries always win.
    """
    pending = [e for e in ledger if e.get("status") == "pending"]
    terminal = [e for e in ledger if e.get("status") in ("consumed", "deferred")]
    recent_terminal = terminal[-recent_terminal_keep:] if recent_terminal_keep > 0 else []

    selected_keys = {id(e) for e in pending + recent_terminal}
    selected = [e for e in ledger if id(e) in selected_keys]
    if len(selected) > max_total:
        # Always preserve pending first, then most recent terminal.
        room_for_terminal = max(0, max_total - len(pending))
        keep_terminal = recent_terminal[-room_for_terminal:] if room_for_terminal else []
        keep_keys = {id(e) for e in pending + keep_terminal}
        selected = [e for e in ledger if id(e) in keep_keys][-max_total:]

    return render_user_message_audit_view(
        selected,
        max_entries=max_total,
        text_max_chars=text_max_chars,
    )


def validate_stored_user_message(row: Any) -> dict[str, Any] | None:
    """Validate a serialized user-message ledger entry from a resume snapshot.

    Returns a normalized dict, or ``None`` if the row is malformed.  Strict on
    structure, permissive on payload content (metadata is opaque).
    """
    if not isinstance(row, Mapping):
        return None
    status = row.get("status")
    if status not in ("pending", "consumed", "deferred"):
        return None
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    raw: dict[str, Any] = {
        "message_id": row.get("message_id"),
        "created_at_epoch_seconds": row.get("created_at_epoch_seconds"),
        "source": row.get("source"),
        "text": row.get("text"),
        "metadata": dict(metadata),
    }
    if isinstance(row.get("_bounds"), Mapping):
        raw["_bounds"] = dict(row["_bounds"])
    normalized = normalize_user_message(raw)
    mid = str(normalized.get("message_id") or "").strip()
    if not mid:
        return None
    out: dict[str, Any] = {
        "message_id": mid,
        "created_at_epoch_seconds": normalized.get("created_at_epoch_seconds"),
        "source": normalized.get("source"),
        "text": normalized.get("text", ""),
        "metadata": dict(normalized.get("metadata") or {}),
        "status": status,
        "received_at_iteration": _coerce_optional_int(row.get("received_at_iteration")),
        "consumed_iteration": _coerce_optional_int(row.get("consumed_iteration")),
        "deferred_iteration": _coerce_optional_int(row.get("deferred_iteration")),
        "defer_reason": _coerce_optional_str(row.get("defer_reason")),
    }
    if "_bounds" in normalized:
        out["_bounds"] = dict(normalized["_bounds"])
    return out


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_str(value: Any) -> str | None:
    if value is None or not isinstance(value, str):
        return None
    s = value.strip()
    return s or None
