"""Generic mutation helpers for harness-emergent resolution items."""
from __future__ import annotations

import uuid
from typing import Any

from .resolution_envelope import (
    MAX_CONTEXT_NOTE_BODY_CHARS,
    MAX_CONTEXT_NOTE_INTENT_CHARS,
    MAX_CONTEXT_NOTES_PER_ITEM,
    MAX_EMERGENT_PROPOSALS_PER_RESOLVER,
    MAX_EMERGENT_REASON_CHARS,
    MAX_EMERGENT_TITLE_CHARS,
    resolution_item_row_dict,
)
from .resolution_lifecycle import (
    EMERGENT_RESOLUTION_ITEM_PREFIX,
    is_allowed_manual_emergent_transition,
    normalize_resolution_item_state,
    stamp_harness_lifecycle_domain,
)


def _normalize_title(title: Any) -> str:
    return str(title or "").strip()[:MAX_EMERGENT_TITLE_CHARS]


def _normalize_reason(reason: Any) -> str:
    return str(reason or "").strip()[:MAX_EMERGENT_REASON_CHARS]


def ledger_decision_keys(ledger: dict[str, Any] | None) -> set[str]:
    if not isinstance(ledger, dict):
        return set()
    out: set[str] = set()
    for row in list(ledger.get("items") or []):
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip().lower()
        if key:
            out.add(key)
    return out


def board_title_fingerprints(items: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for row in items:
        if not isinstance(row, dict):
            continue
        title = _normalize_title(row.get("title"))
        if title:
            out.add(title.casefold())
    return out


def known_item_ids(items: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("item_id") or "").strip()
        for row in items
        if isinstance(row, dict) and str(row.get("item_id") or "").strip()
    }


def evaluate_add_item_promotion(
    proposal: dict[str, Any],
    *,
    ledger_decision_keys_set: set[str],
    board_items: list[dict[str, Any]],
) -> tuple[bool, str]:
    title = _normalize_title(proposal.get("title"))
    if len(title) < 8:
        return False, "title_too_short"
    reason = _normalize_reason(proposal.get("reason"))
    if len(reason) < 24:
        return False, "reason_insufficient_substance"

    if title.casefold() in board_title_fingerprints(board_items):
        return False, "duplicate_title"

    domain_payload = proposal.get("domain_payload") if isinstance(proposal.get("domain_payload"), dict) else {}
    decision_key = str(domain_payload.get("decision_key") or "").strip().lower()
    if decision_key and decision_key in ledger_decision_keys_set:
        return False, "duplicates_existing_ledger_decision"

    materiality = str(proposal.get("materiality") or "medium").strip().lower()
    resolution_condition = str(proposal.get("resolution_condition") or "").strip()
    try:
        priority = int(proposal.get("priority") or 50)
    except (TypeError, ValueError):
        priority = 50
    priority = max(0, min(100, priority))
    dependencies = proposal.get("dependencies") if isinstance(proposal.get("dependencies"), list) else []
    evidence_refs = proposal.get("evidence_refs") if isinstance(proposal.get("evidence_refs"), list) else []
    has_structural_signal = (
        materiality == "high"
        or priority >= 70
        or len(dependencies) > 0
        or len(evidence_refs) > 0
        or len(resolution_condition) >= 16
    )
    if not has_structural_signal:
        return False, "missing_structural_signal_for_new_item"
    if materiality == "low" and len(dependencies) == 0 and len(evidence_refs) <= 1 and len(resolution_condition) < 16 and priority < 70:
        return False, "likely_note_not_item_use_attach_note"
    return True, "ok"


def normalize_resolution_change(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("work_board_change_not_object")
    op = str(raw.get("op") or raw.get("operation") or "").strip().lower()
    if op == "add":
        op = "add_item"
    if op not in {"add_item", "attach_note", "update_item_state"}:
        raise ValueError("invalid_work_board_change_op")
    if op == "add_item":
        materiality = str(raw.get("materiality") or "medium").strip().lower()
        if materiality not in {"low", "medium", "high"}:
            materiality = "medium"
        blocking_impact = raw.get("blocking_impact")
        try:
            priority = int(raw.get("priority")) if raw.get("priority") is not None else 50
        except (TypeError, ValueError):
            priority = 50
        return {
            "op": "add_item",
            "title": _normalize_title(raw.get("title")),
            "kind": str(raw.get("kind") or "").strip()[:128],
            "reason": _normalize_reason(raw.get("reason")),
            "materiality": materiality,
            "blocking_impact": str(blocking_impact).strip()[:64] if blocking_impact is not None else None,
            "resolution_condition": str(raw.get("resolution_condition") or "").strip()[:400] or None,
            "dependencies": [str(x).strip()[:128] for x in list(raw.get("dependencies") or []) if str(x).strip()][:16],
            "evidence_refs": [str(x).strip()[:128] for x in list(raw.get("evidence_refs") or []) if str(x).strip()][:24],
            "alternatives": [str(x).strip()[:160] for x in list(raw.get("alternatives") or []) if str(x).strip()][:16],
            "scope": dict(raw["scope"]) if isinstance(raw.get("scope"), dict) else {},
            "domain_payload": dict(raw["domain_payload"]) if isinstance(raw.get("domain_payload"), dict) else {},
            "context_note": (
                str(raw.get("context_note") or raw.get("attached_note") or "").strip()[:MAX_CONTEXT_NOTE_BODY_CHARS] or None
            ),
            "priority": max(0, min(100, priority)),
            "state": str(raw.get("state") or "open").strip().lower()[:64],
            "summary": str(raw.get("summary") or "").strip()[:500] or None,
        }
    if op == "attach_note":
        target_item_id = str(raw.get("target_item_id") or "").strip()
        if not target_item_id:
            raise ValueError("missing_target_item_id_for_attach_note")
        note = str(raw.get("note") or "").strip()
        if not note or len(note) > MAX_CONTEXT_NOTE_BODY_CHARS:
            raise ValueError("invalid_note_body_for_attach_note")
        return {
            "op": "attach_note",
            "target_item_id": target_item_id,
            "note": note,
            "note_intent": str(raw.get("note_intent") or "").strip()[:MAX_CONTEXT_NOTE_INTENT_CHARS] or None,
        }
    target_item_id = str(raw.get("target_item_id") or "").strip()
    if not target_item_id.startswith(EMERGENT_RESOLUTION_ITEM_PREFIX):
        raise ValueError("update_item_state_emergent_only")
    return {
        "op": "update_item_state",
        "target_item_id": target_item_id,
        "new_state": normalize_resolution_item_state(str(raw.get("new_state") or "")),
        "reason": str(raw.get("reason") or "").strip()[:200] or None,
    }


def normalize_resolution_changes_list(raw: list[Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("missing_work_board_changes")
    out: list[dict[str, Any]] = []
    for row in raw[:MAX_EMERGENT_PROPOSALS_PER_RESOLVER]:
        if isinstance(row, dict):
            out.append(normalize_resolution_change(row))
    if not out:
        raise ValueError("empty_work_board_changes")
    return out


def build_emergent_item_row(proposal: dict[str, Any], *, item_id: str) -> dict[str, Any]:
    context_notes: list[dict[str, Any]] = []
    note = proposal.get("context_note")
    if isinstance(note, str) and note.strip():
        context_notes.append(
            {
                "body": note.strip()[:MAX_CONTEXT_NOTE_BODY_CHARS],
                "intent": None,
                "non_canonical": True,
            }
        )
    state = normalize_resolution_item_state(str(proposal.get("state") or "open"))
    domain_payload = dict(proposal["domain_payload"]) if isinstance(proposal.get("domain_payload"), dict) else {}
    stamped_payload = stamp_harness_lifecycle_domain(domain_payload, new_state=state, reason_code="promoted")
    return resolution_item_row_dict(
        item_id=item_id,
        title=str(proposal.get("title") or ""),
        kind=str(proposal.get("kind") or "work_item"),
        state=state,
        priority=int(proposal.get("priority") or 50),
        materiality=str(proposal.get("materiality") or "medium").strip().lower(),
        blocking_impact=proposal.get("blocking_impact"),
        dependencies=list(proposal.get("dependencies") or []),
        evidence_refs=list(proposal.get("evidence_refs") or []),
        alternatives=list(proposal.get("alternatives") or []),
        resolution_condition=proposal.get("resolution_condition"),
        scope=proposal.get("scope") if isinstance(proposal.get("scope"), dict) else {},
        summary=proposal.get("summary"),
        notes=None,
        context_notes=context_notes,
        provenance="harness.emergent.v1",
        domain_payload=stamped_payload,
    )


def new_emergent_item_id() -> str:
    return f"{EMERGENT_RESOLUTION_ITEM_PREFIX}{uuid.uuid4().hex[:12]}"


def apply_resolution_changes(
    changes: list[dict[str, Any]],
    *,
    decision_ledger: dict[str, Any],
    emergent_items: list[dict[str, Any]],
    context_notes_by_item_id: dict[str, list[dict[str, Any]]],
    projected_ledgers_items: list[dict[str, Any]],
) -> dict[str, Any]:
    ledger_keys = ledger_decision_keys(decision_ledger)
    board_snapshot = [dict(x) for x in projected_ledgers_items if isinstance(x, dict)] + [
        dict(x) for x in emergent_items if isinstance(x, dict)
    ]
    new_emergent = [dict(x) for x in emergent_items if isinstance(x, dict)]
    notes_map: dict[str, list[dict[str, Any]]] = {
        key: [dict(note) for note in value if isinstance(note, dict)]
        for key, value in (context_notes_by_item_id or {}).items()
        if isinstance(value, list)
    }
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for change in changes:
        op = str(change.get("op") or "")
        if op == "add_item":
            ok, code = evaluate_add_item_promotion(
                change,
                ledger_decision_keys_set=ledger_keys,
                board_items=board_snapshot,
            )
            if not ok:
                rejected.append({"op": "add_item", "code": code, "title": change.get("title")})
                continue
            item_id = new_emergent_item_id()
            row = build_emergent_item_row(change, item_id=item_id)
            new_emergent.append(row)
            board_snapshot.append(dict(row))
            accepted.append({"op": "add_item", "item_id": item_id, "title": row.get("title")})
            continue
        if op == "attach_note":
            target_item_id = str(change.get("target_item_id") or "")
            if target_item_id not in known_item_ids(board_snapshot):
                rejected.append({"op": "attach_note", "code": "unknown_target_item_id", "target_item_id": target_item_id})
                continue
            entry = {
                "body": str(change.get("note") or "").strip()[:MAX_CONTEXT_NOTE_BODY_CHARS],
                "intent": change.get("note_intent"),
                "non_canonical": True,
            }
            prior = list(notes_map.get(target_item_id) or [])
            prior.append(entry)
            notes_map[target_item_id] = prior[-MAX_CONTEXT_NOTES_PER_ITEM:]
            accepted.append({"op": "attach_note", "target_item_id": target_item_id})
            continue
        if op == "update_item_state":
            target_item_id = str(change.get("target_item_id") or "").strip()
            new_state = normalize_resolution_item_state(str(change.get("new_state") or ""))
            index = next(
                (
                    i
                    for i, row in enumerate(new_emergent)
                    if isinstance(row, dict) and str(row.get("item_id") or "") == target_item_id
                ),
                -1,
            )
            if index < 0:
                rejected.append({"op": "update_item_state", "code": "unknown_emergent_item", "target_item_id": target_item_id})
                continue
            row = dict(new_emergent[index])
            old_state = str(row.get("state") or "open")
            if not is_allowed_manual_emergent_transition(old_state, new_state):
                rejected.append(
                    {
                        "op": "update_item_state",
                        "code": "invalid_state_transition",
                        "target_item_id": target_item_id,
                        "from": old_state,
                        "to": new_state,
                    }
                )
                continue
            row["state"] = new_state
            row["domain_payload"] = stamp_harness_lifecycle_domain(
                row.get("domain_payload") if isinstance(row.get("domain_payload"), dict) else {},
                new_state=new_state,
                reason_code=f"manual_update:{str(change.get('reason') or 'update').strip()[:80]}",
            )
            new_emergent[index] = row
            accepted.append({"op": "update_item_state", "target_item_id": target_item_id, "new_state": new_state})
            continue
        rejected.append({"op": op or "unknown", "code": "unsupported_op"})

    return {
        "accepted": accepted,
        "rejected": rejected,
        "emergent_items": new_emergent,
        "context_notes_by_item_id": notes_map,
    }
