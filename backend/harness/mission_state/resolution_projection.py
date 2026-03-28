"""Native projection helpers for organized resolution items."""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import ResolutionItem
from .resolution_lifecycle import normalize_resolution_item_state

RESOLUTION_PROJECTION_VERSION = "resolution_projection.v1"

MAX_CONTEXT_NOTE_BODY_CHARS = 280
MAX_CONTEXT_NOTE_INTENT_CHARS = 64
MAX_CONTEXT_NOTES_PER_ITEM = 6
MAX_EMERGENT_PROPOSALS_PER_RESOLVER = 12
MAX_EMERGENT_REASON_CHARS = 280
MAX_EMERGENT_TITLE_CHARS = 240


def is_resolution_projection(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if str(payload.get("schema_version") or "").strip() != RESOLUTION_PROJECTION_VERSION:
        return False
    return isinstance(payload.get("items"), list)


def new_resolution_projection(
    *,
    domain_projection: str,
    items: list[ResolutionItem | dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_items: list[dict[str, Any]] = []
    for row in items or []:
        if isinstance(row, ResolutionItem):
            normalized_items.append(row.model_dump(mode="json"))
        elif isinstance(row, dict):
            normalized_items.append(dict(row))
    return {
        "schema_version": RESOLUTION_PROJECTION_VERSION,
        "domain_projection": _clean_text(domain_projection, limit=128) or "unknown",
        "items": normalized_items,
    }


def resolution_item_row_dict(
    *,
    item_id: str,
    title: str,
    kind: str,
    state: str,
    priority: int = 50,
    materiality: str = "medium",
    blocking_impact: str | None = None,
    dependencies: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    alternatives: list[str] | None = None,
    resolution_condition: str | None = None,
    scope: Mapping[str, Any] | None = None,
    summary: str | None = None,
    notes: str | None = None,
    context_notes: list[dict[str, Any]] | None = None,
    provenance: str | None = None,
    domain_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "item_id": _clean_text(item_id, limit=128) or "unknown_item",
        "title": _clean_text(title, limit=240) or "Untitled item",
        "kind": _clean_text(kind, limit=128) or "work_item",
        "state": normalize_resolution_item_state(state),
        "priority": _normalize_priority(priority),
        "materiality": _normalize_materiality(materiality),
        "blocking_impact": _clean_text(blocking_impact, limit=64),
        "dependencies": _clean_str_list(dependencies, limit=16, item_limit=128),
        "evidence_refs": _clean_str_list(evidence_refs, limit=24, item_limit=128),
        "alternatives": _clean_str_list(alternatives, limit=16, item_limit=160),
        "resolution_condition": _clean_text(resolution_condition, limit=400),
        "scope": dict(scope) if isinstance(scope, Mapping) else {},
        "summary": _clean_text(summary, limit=500),
        "notes": _clean_text(notes, limit=500),
        "context_notes": _clean_context_notes(context_notes),
        "provenance": _clean_text(provenance, limit=128),
        "domain_payload": dict(domain_payload) if isinstance(domain_payload, Mapping) else {},
    }


def _normalize_priority(value: Any) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        priority = 50
    return max(0, min(100, priority))


def _normalize_materiality(value: Any) -> str:
    materiality = str(value or "medium").strip().lower()
    return materiality if materiality in {"low", "medium", "high"} else "medium"


def _clean_context_notes(values: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in values or []:
        if not isinstance(row, dict):
            continue
        body = _clean_text(row.get("body"), limit=MAX_CONTEXT_NOTE_BODY_CHARS)
        if not body:
            continue
        out.append(
            {
                "body": body,
                "intent": _clean_text(row.get("intent"), limit=MAX_CONTEXT_NOTE_INTENT_CHARS),
                "non_canonical": bool(row.get("non_canonical")),
            }
        )
        if len(out) >= MAX_CONTEXT_NOTES_PER_ITEM:
            break
    return out


def _clean_str_list(values: list[str] | None, *, limit: int, item_limit: int) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = _clean_text(value, limit=item_limit)
        if not text or text in out:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _clean_text(value: Any, *, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] if text else None
