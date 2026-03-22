"""Mission-agnostic organized-work item contract (harness-owned).

Canonical product name: **decision ledger** (see ``harness.decision_ledger``).
``WORK_BOARD_VERSION`` / ``work_board.v1`` is the **stable JSON wire id** for the same
envelope (historical module name); new code should think “decision ledger envelope,”
not a separate “work board” product.
"""
from __future__ import annotations

import time
from typing import Any, Literal

WORK_BOARD_VERSION = "work_board.v1"

# Emergent item / note bounds (harness layer — not domain ontology).
MAX_EMERGENT_PROPOSALS_PER_RESOLVER = 8
MAX_BOARD_CONTEXT_NOTES_PER_ITEM = 3
MAX_CONTEXT_NOTE_BODY_CHARS = 280
MAX_CONTEXT_NOTE_INTENT_CHARS = 64
MAX_EMERGENT_REASON_CHARS = 720
MAX_EMERGENT_TITLE_CHARS = 240

# Generic lifecycle — aligns with shared blocker vocabulary where overlap exists.
WorkBoardItemState = Literal[
    "open",
    "investigating",
    "narrowed",
    "blocked",
    "waiting_human",
    "waiting_evidence",
    "answered_pending_integration",
    "resolved",
    "superseded",
]


def new_work_board(*, domain_projection: str, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return a versioned work-board envelope (JSON-serializable).

    Parameters
    ----------
    domain_projection:
        Owning projection id e.g. ``transcript_edit.decision_ledger``.
    items:
        List of :func:`work_board_item_dict` rows.
    """
    return {
        "schema_version": WORK_BOARD_VERSION,
        "updated_at_epoch_seconds": int(time.time()),
        "domain_projection": str(domain_projection or "").strip() or "unknown",
        "items": list(items or []),
    }


def work_board_item_dict(
    *,
    item_id: str,
    title: str,
    kind: str,
    state: WorkBoardItemState | str,
    priority: int = 50,
    materiality: Literal["low", "medium", "high"] = "medium",
    blocking_impact: str | None = None,
    dependencies: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    alternatives: list[str] | None = None,
    resolution_condition: str | None = None,
    scope: dict[str, Any] | None = None,
    summary: str | None = None,
    notes: str | None = None,
    context_notes: list[dict[str, Any]] | None = None,
    provenance: str | None = None,
    domain_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One normalized board row (flat JSON).

    ``blocking_impact`` is an optional opaque string from the domain resolver; shared harness
    code treats it as payload only and does not branch on mission-specific label values.
    """
    cn_raw = context_notes if isinstance(context_notes, list) else []
    cn_out: list[dict[str, Any]] = []
    for row in cn_raw[:MAX_BOARD_CONTEXT_NOTES_PER_ITEM]:
        if not isinstance(row, dict):
            continue
        body = str(row.get("body") or "").strip()[:MAX_CONTEXT_NOTE_BODY_CHARS]
        if not body:
            continue
        cn_out.append(
            {
                "body": body,
                "intent": str(row.get("intent") or "").strip()[:MAX_CONTEXT_NOTE_INTENT_CHARS] or None,
                "non_canonical": True,
            }
        )
    return {
        "item_id": str(item_id or "").strip(),
        "title": str(title or "").strip()[:240],
        "kind": str(kind or "").strip()[:128],
        "state": str(state or "open").strip().lower()[:64],
        "priority": int(priority),
        "materiality": str(materiality or "medium").strip().lower(),
        "blocking_impact": (
            str(blocking_impact).strip()[:64] if blocking_impact is not None else None
        ),
        "dependencies": [str(x).strip()[:128] for x in (dependencies or []) if str(x).strip()][:16],
        "evidence_refs": [str(x).strip()[:128] for x in (evidence_refs or []) if str(x).strip()][:24],
        "alternatives": [str(x).strip()[:160] for x in (alternatives or []) if str(x).strip()][:16],
        "resolution_condition": (
            str(resolution_condition).strip()[:400] if resolution_condition else None
        ),
        "scope": dict(scope) if isinstance(scope, dict) else {},
        "summary": str(summary).strip()[:500] if summary else None,
        "notes": str(notes).strip()[:500] if notes else None,
        "context_notes": cn_out,
        "provenance": str(provenance).strip()[:128] if provenance else None,
        "domain_payload": dict(domain_payload) if isinstance(domain_payload, dict) else {},
    }
