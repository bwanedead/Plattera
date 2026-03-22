"""Emergent board-item proposals, promotion rules, and bounded context notes (harness).

Domain missions supply ``domain_payload`` and kinds as hints; harness rules stay generic.
"""
from __future__ import annotations

import uuid
from typing import Any

from .lifecycle import (
    EMERGENT_ITEM_ID_PREFIX,
    is_allowed_manual_emergent_transition,
    normalize_board_state,
    stamp_harness_lifecycle_domain,
)
from .contracts import (
    MAX_BOARD_CONTEXT_NOTES_PER_ITEM,
    MAX_CONTEXT_NOTE_BODY_CHARS,
    MAX_CONTEXT_NOTE_INTENT_CHARS,
    MAX_EMERGENT_PROPOSALS_PER_RESOLVER,
    MAX_EMERGENT_REASON_CHARS,
    MAX_EMERGENT_TITLE_CHARS,
    work_board_item_dict,
)

def _norm_title(title: Any) -> str:
    return str(title or "").strip()[:MAX_EMERGENT_TITLE_CHARS]


def _norm_reason(reason: Any) -> str:
    return str(reason or "").strip()[:MAX_EMERGENT_REASON_CHARS]


def ledger_decision_keys(ledger: dict[str, Any] | None) -> set[str]:
    if not isinstance(ledger, dict):
        return set()
    out: set[str] = set()
    for row in list(ledger.get("items") or []):
        if isinstance(row, dict):
            k = str(row.get("key") or "").strip().lower()
            if k:
                out.add(k)
    return out


def board_title_fingerprints(items: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for row in items:
        if not isinstance(row, dict):
            continue
        t = _norm_title(row.get("title"))
        if t:
            out.add(t.casefold())
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
    """Return (accept, rejection_code_or_ok). Ledger-primary duplicate detection."""
    title = _norm_title(proposal.get("title"))
    if len(title) < 8:
        return False, "title_too_short"
    reason = _norm_reason(proposal.get("reason"))
    if len(reason) < 24:
        return False, "reason_insufficient_substance"

    titles = board_title_fingerprints(board_items)
    if title.casefold() in titles:
        return False, "duplicate_title"

    dp = proposal.get("domain_payload") if isinstance(proposal.get("domain_payload"), dict) else {}
    dk = str(dp.get("decision_key") or "").strip().lower()
    if dk and dk in ledger_decision_keys_set:
        return False, "duplicates_existing_ledger_decision"

    mat = str(proposal.get("materiality") or "medium").strip().lower()
    rc = str(proposal.get("resolution_condition") or "").strip()
    try:
        pri = int(proposal.get("priority") or 50)
    except (TypeError, ValueError):
        pri = 50
    pri = max(0, min(100, pri))
    deps = proposal.get("dependencies") if isinstance(proposal.get("dependencies"), list) else []
    ev = proposal.get("evidence_refs") if isinstance(proposal.get("evidence_refs"), list) else []
    # Structural gating uses only generic signals. ``blocking_impact`` is stored but not
    # interpreted here — domain packs own mission-specific labels (Phase 29).
    has_structural_signal = (
        mat == "high"
        or pri >= 70
        or len(deps) > 0
        or len(ev) > 0
        or len(rc) >= 16
    )
    if not has_structural_signal:
        return False, "missing_structural_signal_for_new_item"

    if (
        mat == "low"
        and len(deps) == 0
        and len(ev) <= 1
        and len(rc) < 16
        and pri < 70
    ):
        return False, "likely_note_not_item_use_attach_note"

    return True, "ok"


def normalize_work_board_change(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate one resolver change operation; raises ValueError on invalid shape."""
    if not isinstance(raw, dict):
        raise ValueError("work_board_change_not_object")
    op = str(raw.get("op") or raw.get("operation") or "").strip().lower()
    if op == "add":
        op = "add_item"
    if op not in {"add_item", "attach_note", "update_item_state"}:
        raise ValueError("invalid_work_board_change_op")
    if op == "add_item":
        title = _norm_title(raw.get("title"))
        kind = str(raw.get("kind") or "").strip()[:128]
        if not kind:
            raise ValueError("missing_kind_for_add_item")
        reason = _norm_reason(raw.get("reason"))
        materiality = str(raw.get("materiality") or "medium").strip().lower()
        if materiality not in {"low", "medium", "high"}:
            materiality = "medium"
        blocking_impact = raw.get("blocking_impact")
        bi = str(blocking_impact).strip()[:64] if blocking_impact is not None else None
        deps = [str(x).strip()[:128] for x in list(raw.get("dependencies") or []) if str(x).strip()][:16]
        ev = [str(x).strip()[:128] for x in list(raw.get("evidence_refs") or []) if str(x).strip()][:24]
        alts = [str(x).strip()[:160] for x in list(raw.get("alternatives") or []) if str(x).strip()][:16]
        rc = str(raw.get("resolution_condition") or "").strip()[:400] or None
        scope = dict(raw["scope"]) if isinstance(raw.get("scope"), dict) else {}
        dp = dict(raw["domain_payload"]) if isinstance(raw.get("domain_payload"), dict) else {}
        cn = str(raw.get("context_note") or raw.get("attached_note") or "").strip()[:MAX_CONTEXT_NOTE_BODY_CHARS] or None
        priority_raw = raw.get("priority")
        try:
            priority = int(priority_raw) if priority_raw is not None else 50
        except (TypeError, ValueError):
            priority = 50
        return {
            "op": "add_item",
            "title": title,
            "kind": kind,
            "reason": reason,
            "materiality": materiality,
            "blocking_impact": bi,
            "resolution_condition": rc,
            "dependencies": deps,
            "evidence_refs": ev,
            "alternatives": alts,
            "scope": scope,
            "domain_payload": dp,
            "context_note": cn,
            "priority": max(0, min(100, priority)),
            "state": str(raw.get("state") or "open").strip().lower()[:64],
            "summary": str(raw.get("summary") or "").strip()[:500] or None,
        }
    if op == "attach_note":
        target = str(raw.get("target_item_id") or "").strip()
        if not target:
            raise ValueError("missing_target_item_id_for_attach_note")
        note = str(raw.get("note") or "").strip()
        if not note or len(note) > MAX_CONTEXT_NOTE_BODY_CHARS:
            raise ValueError("invalid_note_body_for_attach_note")
        intent = str(raw.get("note_intent") or "").strip()[:MAX_CONTEXT_NOTE_INTENT_CHARS] or None
        return {
            "op": "attach_note",
            "target_item_id": target,
            "note": note,
            "note_intent": intent,
        }
    if op == "update_item_state":
        target_u = str(raw.get("target_item_id") or "").strip()
        if not target_u.startswith(EMERGENT_ITEM_ID_PREFIX):
            raise ValueError("update_item_state_emergent_only")
        new_state = normalize_board_state(str(raw.get("new_state") or ""))
        reason = str(raw.get("reason") or "").strip()[:200] or None
        return {
            "op": "update_item_state",
            "target_item_id": target_u,
            "new_state": new_state,
            "reason": reason,
        }
    raise ValueError("invalid_work_board_change_op")


def normalize_work_board_changes_list(raw: list[Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("missing_work_board_changes")
    out: list[dict[str, Any]] = []
    for row in raw[:MAX_EMERGENT_PROPOSALS_PER_RESOLVER]:
        if isinstance(row, dict):
            out.append(normalize_work_board_change(row))
    if not out:
        raise ValueError("empty_work_board_changes")
    return out


def build_emergent_item_row(proposal: dict[str, Any], *, item_id: str) -> dict[str, Any]:
    """Create a durable board row from a normalized add_item proposal."""
    cn: list[dict[str, Any]] = []
    note = proposal.get("context_note")
    if isinstance(note, str) and note.strip():
        cn.append({"body": note.strip()[:MAX_CONTEXT_NOTE_BODY_CHARS], "intent": None, "non_canonical": True})
    state_s = normalize_board_state(str(proposal.get("state") or "open"))
    dp_in = dict(proposal["domain_payload"]) if isinstance(proposal.get("domain_payload"), dict) else {}
    dp_stamped = stamp_harness_lifecycle_domain(dp_in, new_state=state_s, reason_code="promoted")
    return work_board_item_dict(
        item_id=item_id,
        title=str(proposal.get("title") or ""),
        kind=str(proposal.get("kind") or "work_item"),
        state=state_s,
        priority=int(proposal.get("priority") or 50),
        materiality=str(proposal.get("materiality") or "medium").strip().lower(),  # type: ignore[arg-type]
        blocking_impact=proposal.get("blocking_impact"),
        dependencies=list(proposal.get("dependencies") or []),
        evidence_refs=list(proposal.get("evidence_refs") or []),
        alternatives=list(proposal.get("alternatives") or []),
        resolution_condition=proposal.get("resolution_condition"),
        scope=proposal.get("scope") if isinstance(proposal.get("scope"), dict) else {},
        summary=proposal.get("summary"),
        notes=None,
        context_notes=cn,
        provenance="harness.emergent.v1",
        domain_payload=dp_stamped,
    )


def new_emergent_item_id() -> str:
    return f"harness:emergent:{uuid.uuid4().hex[:12]}"


def apply_work_board_changes(
    changes: list[dict[str, Any]],
    *,
    decision_ledger: dict[str, Any],
    emergent_items: list[dict[str, Any]],
    context_notes_by_item_id: dict[str, list[dict[str, Any]]],
    projected_ledgers_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply normalized changes; returns audit + updated emergent list + notes map (copies)."""
    ledger_keys = ledger_decision_keys(decision_ledger)
    board_snapshot = [dict(x) for x in projected_ledgers_items if isinstance(x, dict)] + [
        dict(x) for x in emergent_items if isinstance(x, dict)
    ]
    new_emergent = [dict(x) for x in emergent_items if isinstance(x, dict)]
    notes_map: dict[str, list[dict[str, Any]]] = {
        k: [dict(n) for n in v if isinstance(n, dict)]
        for k, v in (context_notes_by_item_id or {}).items()
        if isinstance(v, list)
    }
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for ch in changes:
        op = str(ch.get("op") or "")
        if op == "add_item":
            ok, code = evaluate_add_item_promotion(ch, ledger_decision_keys_set=ledger_keys, board_items=board_snapshot)
            if not ok:
                rejected.append({"op": "add_item", "code": code, "title": ch.get("title")})
                continue
            item_id = new_emergent_item_id()
            row = build_emergent_item_row(ch, item_id=item_id)
            new_emergent.append(row)
            board_snapshot.append(dict(row))
            accepted.append({"op": "add_item", "item_id": item_id, "title": row.get("title")})
            continue
        if op == "attach_note":
            tid = str(ch.get("target_item_id") or "")
            known = known_item_ids(board_snapshot)
            if tid not in known:
                rejected.append({"op": "attach_note", "code": "unknown_target_item_id", "target_item_id": tid})
                continue
            entry: dict[str, Any] = {
                "body": str(ch.get("note") or "").strip()[:MAX_CONTEXT_NOTE_BODY_CHARS],
                "intent": ch.get("note_intent"),
                "non_canonical": True,
            }
            prev = list(notes_map.get(tid) or [])
            prev.append(entry)
            notes_map[tid] = prev[-MAX_BOARD_CONTEXT_NOTES_PER_ITEM:]
            accepted.append({"op": "attach_note", "target_item_id": tid})
            continue
        if op == "update_item_state":
            tid = str(ch.get("target_item_id") or "").strip()
            new_s = normalize_board_state(str(ch.get("new_state") or ""))
            idx = next((i for i, r in enumerate(new_emergent) if isinstance(r, dict) and str(r.get("item_id") or "") == tid), -1)
            if idx < 0:
                rejected.append({"op": "update_item_state", "code": "unknown_emergent_item", "target_item_id": tid})
                continue
            row = dict(new_emergent[idx])
            old_s = str(row.get("state") or "open")
            if not is_allowed_manual_emergent_transition(old_s, new_s):
                rejected.append(
                    {
                        "op": "update_item_state",
                        "code": "invalid_state_transition",
                        "target_item_id": tid,
                        "from": old_s,
                        "to": new_s,
                    }
                )
                continue
            row["state"] = new_s
            row["domain_payload"] = stamp_harness_lifecycle_domain(
                row.get("domain_payload") if isinstance(row.get("domain_payload"), dict) else {},
                new_state=new_s,
                reason_code=str(ch.get("reason") or "update_item_state").strip()[:120] or "update_item_state",
            )
            new_emergent[idx] = row
            for j, snap in enumerate(board_snapshot):
                if isinstance(snap, dict) and str(snap.get("item_id") or "") == tid:
                    board_snapshot[j] = dict(row)
                    break
            accepted.append({"op": "update_item_state", "target_item_id": tid, "new_state": new_s})
            continue
        rejected.append({"op": op or "unknown", "code": "unsupported_change"})

    return {
        "emergent_items": new_emergent,
        "context_notes_by_item_id": notes_map,
        "accepted": accepted,
        "rejected": rejected,
    }
