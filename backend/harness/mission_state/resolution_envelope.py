from __future__ import annotations

import time
from typing import Any, Literal

from .compat import LEGACY_WORK_BOARD_ENVELOPE_VERSION

# Bounded generic row shaping for compatibility envelopes.
MAX_EMERGENT_PROPOSALS_PER_RESOLVER = 8
MAX_CONTEXT_NOTES_PER_ITEM = 3
MAX_CONTEXT_NOTE_BODY_CHARS = 280
MAX_CONTEXT_NOTE_INTENT_CHARS = 64
MAX_EMERGENT_REASON_CHARS = 720
MAX_EMERGENT_TITLE_CHARS = 240

ResolutionItemStatus = Literal[
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


def new_resolution_envelope(
    *,
    domain_projection: str,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the legacy compatibility envelope for generic resolution rows."""
    return {
        "schema_version": LEGACY_WORK_BOARD_ENVELOPE_VERSION,
        "updated_at_epoch_seconds": int(time.time()),
        "domain_projection": str(domain_projection or "").strip() or "unknown",
        "items": list(items or []),
    }


def resolution_item_row_dict(
    *,
    item_id: str,
    title: str,
    kind: str,
    state: ResolutionItemStatus | str,
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
    """Build one normalized compatibility row for a generic resolution item."""
    raw_notes = context_notes if isinstance(context_notes, list) else []
    notes_out: list[dict[str, Any]] = []
    for row in raw_notes[:MAX_CONTEXT_NOTES_PER_ITEM]:
        if not isinstance(row, dict):
            continue
        body = str(row.get("body") or "").strip()[:MAX_CONTEXT_NOTE_BODY_CHARS]
        if not body:
            continue
        notes_out.append(
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
        "blocking_impact": str(blocking_impact).strip()[:64] if blocking_impact is not None else None,
        "dependencies": [str(x).strip()[:128] for x in (dependencies or []) if str(x).strip()][:16],
        "evidence_refs": [str(x).strip()[:128] for x in (evidence_refs or []) if str(x).strip()][:24],
        "alternatives": [str(x).strip()[:160] for x in (alternatives or []) if str(x).strip()][:16],
        "resolution_condition": str(resolution_condition).strip()[:400] if resolution_condition else None,
        "scope": dict(scope) if isinstance(scope, dict) else {},
        "summary": str(summary).strip()[:500] if summary else None,
        "notes": str(notes).strip()[:500] if notes else None,
        "context_notes": notes_out,
        "provenance": str(provenance).strip()[:128] if provenance else None,
        "domain_payload": dict(domain_payload) if isinstance(domain_payload, dict) else {},
    }
