"""Append-only HITL exchange ledger — durable mechanical history of each
human-in-the-loop interaction.

Each ledger entry captures:
  - the exact outbound request payload sent to the operator
  - the exact inbound response payload (when answered)
  - mechanical consumption status (when the agent declares the answer integrated)

The ledger is intentionally separate from ``HitlTransportPosture``: the latter
is the live transport queue (pending → waiting → answered_unintegrated → consumed),
the former is durable history that survives consumption.

No semantic interpretation lives here.  The ledger does not judge whether the
human answer was "correct" or "sufficient" — it only records mechanical facts.

Generic across harness domains (transcript edit, mapping, etc.); the ledger
must not encode pack-specific schemas.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from .feedback_shape import normalize_hitl_feedback

LedgerExchangeStatus = Literal["pending", "answered", "consumed"]

# Bounded compaction: drop only old *consumed* exchanges past this cap.
# Pending and answered exchanges are never dropped — losing them would erase
# active or audit-critical state.
_MAX_LEDGER_TOTAL = 256
_MAX_CONSUMED_RETAINED = 64

EXCHANGE_ID_PREFIX = "hitl:"


def make_exchange_id(prompt_id: str) -> str:
    pid = str(prompt_id or "").strip()
    if not pid:
        return ""
    return f"{EXCHANGE_ID_PREFIX}{pid}"


def _normalize_request_payload(payload: Any) -> dict[str, Any]:
    """Normalize an outbound HITL request payload to a JSON-safe dict.

    Accepts the result of ``normalize_hitl_request`` (already a dict) or any
    Mapping; returns a shallow copy with stable key shape.
    """
    if not isinstance(payload, Mapping):
        return {}
    out: dict[str, Any] = dict(payload)
    return out


def _normalize_response_payload(payload: Any) -> dict[str, Any]:
    """Defensive size-bounded normalization for inbound response payloads.

    The transport layer (``hitl_poll_feedback_store``) already normalizes
    inbound feedback once at admission.  This second pass guards against
    direct ledger writes (e.g. resume-preseeded responses, future entry
    points) and is idempotent on already-bounded payloads.
    """
    if not isinstance(payload, Mapping):
        return {}
    return normalize_hitl_feedback(payload)


def _find_index_by_prompt_id(ledger: list[dict[str, Any]], prompt_id: str) -> int:
    pid = str(prompt_id or "").strip()
    if not pid:
        return -1
    for idx, entry in enumerate(ledger):
        if str(entry.get("prompt_id") or "").strip() == pid:
            return idx
    return -1


def record_outbound(
    ledger: list[dict[str, Any]],
    *,
    prompt_id: str,
    request_payload: Mapping[str, Any] | None,
    iteration: int,
    blocking: bool,
) -> list[dict[str, Any]]:
    """Append or upsert an exchange for an outbound HITL request.

    Idempotent on ``prompt_id``: if the same prompt_id is recorded twice
    (e.g., resume + replay), the existing entry is preserved with status and
    response intact, but the request payload is refreshed.

    Returns the new ledger list; original is not mutated.
    """
    pid = str(prompt_id or "").strip()
    if not pid:
        return list(ledger)
    new_ledger = list(ledger)
    idx = _find_index_by_prompt_id(new_ledger, pid)
    request_norm = _normalize_request_payload(request_payload)
    if idx >= 0:
        existing = dict(new_ledger[idx])
        existing["request"] = request_norm
        existing["blocking"] = bool(blocking)
        new_ledger[idx] = existing
    else:
        entry = {
            "exchange_id": make_exchange_id(pid),
            "prompt_id": pid,
            "blocking": bool(blocking),
            "issued_at_iteration": int(iteration),
            "request": request_norm,
            "response": None,
            "received_at_iteration": None,
            "consumed_at_iteration": None,
            "status": "pending",
        }
        new_ledger.append(entry)
    return clamp_ledger(new_ledger)


def record_inbound(
    ledger: list[dict[str, Any]],
    *,
    prompt_id: str,
    response_payload: Mapping[str, Any] | None,
    iteration: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Attach exact response payload to the matching exchange.

    Returns ``(new_ledger, newly_answered)``.  ``newly_answered`` is True
    when this call transitions the exchange from ``pending`` to ``answered``;
    False when the exchange already had a response (idempotent re-poll) or no
    matching pending exchange exists.

    If no exchange exists for the prompt_id (e.g. resume case where outbound
    was never recorded), one is synthesized with empty request payload so the
    response is not silently dropped.
    """
    pid = str(prompt_id or "").strip()
    if not pid:
        return list(ledger), False
    new_ledger = list(ledger)
    idx = _find_index_by_prompt_id(new_ledger, pid)
    response_norm = _normalize_response_payload(response_payload)
    if idx < 0:
        # Synthesize a stub — preserves the inbound even without a recorded outbound.
        entry = {
            "exchange_id": make_exchange_id(pid),
            "prompt_id": pid,
            "blocking": False,
            "issued_at_iteration": None,
            "request": {},
            "response": response_norm,
            "received_at_iteration": int(iteration),
            "consumed_at_iteration": None,
            "status": "answered",
        }
        new_ledger.append(entry)
        return clamp_ledger(new_ledger), True
    existing = dict(new_ledger[idx])
    if existing.get("response") is not None and existing.get("status") in ("answered", "consumed"):
        # Idempotent: don't overwrite or move backwards.
        return new_ledger, False
    existing["response"] = response_norm
    existing["received_at_iteration"] = int(iteration)
    if existing.get("status") == "pending":
        existing["status"] = "answered"
    new_ledger[idx] = existing
    return clamp_ledger(new_ledger), True


def mark_consumed(
    ledger: list[dict[str, Any]],
    *,
    prompt_ids: tuple[str, ...] | list[str],
    iteration: int,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Mark matching exchanges as consumed; record consumed_at_iteration.

    Returns ``(new_ledger, matched_ids, unknown_ids)``.  An unknown id is one
    declared by the agent that has no matching exchange — useful for surfacing
    integration drift without modifying ledger.
    """
    want = [str(x).strip() for x in (prompt_ids or ()) if str(x).strip()]
    if not want:
        return list(ledger), [], []
    new_ledger = list(ledger)
    matched: list[str] = []
    unknown: list[str] = []
    for pid in want:
        idx = _find_index_by_prompt_id(new_ledger, pid)
        if idx < 0:
            unknown.append(pid)
            continue
        existing = dict(new_ledger[idx])
        if existing.get("status") != "consumed":
            existing["status"] = "consumed"
            existing["consumed_at_iteration"] = int(iteration)
        matched.append(pid)
        new_ledger[idx] = existing
    return clamp_ledger(new_ledger), matched, unknown


def clamp_ledger(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bounded compaction: drop oldest *consumed* entries past the retention cap.

    Pending/answered entries are never dropped here.  Hard ceiling
    ``_MAX_LEDGER_TOTAL`` only applies after consumed-only compaction.
    """
    if len(ledger) <= _MAX_LEDGER_TOTAL:
        # Even within the total cap, trim consumed-only excess.
        consumed = [e for e in ledger if e.get("status") == "consumed"]
        if len(consumed) <= _MAX_CONSUMED_RETAINED:
            return list(ledger)
        # Drop oldest consumed beyond retention cap (preserve order otherwise).
        keep_consumed_ids = set(id(e) for e in consumed[-_MAX_CONSUMED_RETAINED:])
        return [e for e in ledger if e.get("status") != "consumed" or id(e) in keep_consumed_ids]
    # Hard ceiling exceeded: keep all non-consumed + most recent consumed.
    non_consumed = [e for e in ledger if e.get("status") != "consumed"]
    consumed = [e for e in ledger if e.get("status") == "consumed"]
    consumed_keep = consumed[-_MAX_CONSUMED_RETAINED:]
    return non_consumed + consumed_keep


def count_pending(ledger: list[dict[str, Any]]) -> int:
    return sum(1 for e in ledger if e.get("status") == "pending")


def count_answered_unconsumed(ledger: list[dict[str, Any]]) -> int:
    return sum(1 for e in ledger if e.get("status") == "answered")


def count_consumed(ledger: list[dict[str, Any]]) -> int:
    return sum(1 for e in ledger if e.get("status") == "consumed")


def get_exchange(ledger: list[dict[str, Any]], prompt_id: str) -> dict[str, Any] | None:
    idx = _find_index_by_prompt_id(ledger, prompt_id)
    if idx < 0:
        return None
    return dict(ledger[idx])


def render_ledger_audit_view(
    ledger: list[dict[str, Any]],
    *,
    max_entries: int = 32,
    message_max_chars: int = 400,
    note_max_chars: int = 400,
) -> list[dict[str, Any]]:
    """Projection-only audit view for human timeline rendering.

    Renders each exchange to a compact, audit-friendly dict.  Read-only —
    consumers (UI, audit reports) treat this as a derived projection of the
    canonical ledger, not a source of truth.
    """
    rendered: list[dict[str, Any]] = []
    for entry in ledger[-max_entries:]:
        request = entry.get("request") if isinstance(entry.get("request"), Mapping) else {}
        response = entry.get("response") if isinstance(entry.get("response"), Mapping) else None
        message = str(request.get("message") or "")
        if len(message) > message_max_chars:
            message = message[:message_max_chars] + "…"
        choices = list(request.get("choices") or [])
        context = dict(request.get("context") or {}) if isinstance(request.get("context"), Mapping) else {}
        evidence_refs = list(request.get("evidence_refs") or []) if isinstance(request.get("evidence_refs"), list) else []
        view: dict[str, Any] = {
            "exchange_id": entry.get("exchange_id"),
            "prompt_id": entry.get("prompt_id"),
            "status": entry.get("status"),
            "blocking": bool(entry.get("blocking", False)),
            "issued_at_iteration": entry.get("issued_at_iteration"),
            "received_at_iteration": entry.get("received_at_iteration"),
            "consumed_at_iteration": entry.get("consumed_at_iteration"),
            "request": {
                "message": message,
                "choices": choices,
                "context": context,
                "evidence_refs": evidence_refs,
            },
        }
        if response is not None:
            note = str(response.get("note") or "")
            display_note_truncated = False
            if len(note) > note_max_chars:
                note = note[:note_max_chars] + "…"
                display_note_truncated = True
            response_view: dict[str, Any] = {
                "choice": response.get("choice"),
                "note": note,
                "metadata": dict(response.get("metadata") or {}) if isinstance(response.get("metadata"), Mapping) else {},
                "submitted_at_epoch_seconds": response.get("submitted_at_epoch_seconds"),
            }
            # Carry forward admission-time truncation markers from feedback_shape.
            admission_bounds = response.get("_bounds") if isinstance(response.get("_bounds"), Mapping) else None
            if admission_bounds or display_note_truncated:
                merged_bounds: dict[str, bool] = {}
                if isinstance(admission_bounds, Mapping):
                    for k, v in admission_bounds.items():
                        merged_bounds[str(k)] = bool(v)
                if display_note_truncated:
                    merged_bounds["note_display_truncated"] = True
                response_view["_bounds"] = merged_bounds
            view["response"] = response_view
        else:
            view["response"] = None
        rendered.append(view)
    return rendered


def build_prompt_ledger_view(
    ledger: list[dict[str, Any]],
    *,
    max_total: int = 16,
    recent_consumed_keep: int = 3,
    message_max_chars: int = 400,
    note_max_chars: int = 400,
) -> list[dict[str, Any]]:
    """Bounded ledger view for prompt projection.

    Inclusion policy (mechanical, no semantics):
    - All ``pending`` exchanges (full request, no response yet).
    - All ``answered`` exchanges (full request AND full response).
    - Most recent ``recent_consumed_keep`` ``consumed`` exchanges, full payloads.
    - Older ``consumed`` exchanges omitted.

    Total result is capped at ``max_total`` (newest first within each bucket,
    but ordering preserves ledger insertion order to keep iteration_index sane).
    """
    pending_or_answered = [
        e for e in ledger if e.get("status") in ("pending", "answered")
    ]
    consumed = [e for e in ledger if e.get("status") == "consumed"]
    recent_consumed = consumed[-recent_consumed_keep:] if recent_consumed_keep > 0 else []

    selected_keys = {id(e) for e in pending_or_answered + recent_consumed}
    selected = [e for e in ledger if id(e) in selected_keys]
    if len(selected) > max_total:
        # Always preserve pending/answered first, then most recent consumed.
        keep_consumed = recent_consumed[-(max_total - len(pending_or_answered)) :] if len(pending_or_answered) < max_total else []
        keep_keys = {id(e) for e in pending_or_answered + keep_consumed}
        selected = [e for e in ledger if id(e) in keep_keys][-max_total:]

    return render_ledger_audit_view(
        selected,
        max_entries=max_total,
        message_max_chars=message_max_chars,
        note_max_chars=note_max_chars,
    )


def validate_stored_ledger_entry(row: Any) -> dict[str, Any] | None:
    """Validate a serialized ledger entry from a resume snapshot.

    Returns a normalized dict, or ``None`` if the row is malformed.  Strict on
    structure, permissive on payload content (request/response are opaque dicts).
    """
    if not isinstance(row, Mapping):
        return None
    pid = str(row.get("prompt_id") or "").strip()
    if not pid:
        return None
    status = row.get("status")
    if status not in ("pending", "answered", "consumed"):
        return None
    request = row.get("request") if isinstance(row.get("request"), Mapping) else {}
    response = row.get("response") if isinstance(row.get("response"), Mapping) else None
    out: dict[str, Any] = {
        "exchange_id": str(row.get("exchange_id") or make_exchange_id(pid)),
        "prompt_id": pid,
        "blocking": bool(row.get("blocking", False)),
        "issued_at_iteration": _coerce_optional_int(row.get("issued_at_iteration")),
        "request": dict(request),
        "response": dict(response) if response is not None else None,
        "received_at_iteration": _coerce_optional_int(row.get("received_at_iteration")),
        "consumed_at_iteration": _coerce_optional_int(row.get("consumed_at_iteration")),
        "status": status,
    }
    return out


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
