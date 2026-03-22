"""Generic orientation / startup document coercion (mission-agnostic).

Domain packs map rows into mission-native surfaces. This module must not assign
transcript-edit or mapping-specific posture; it only emits generic ``impact_tier``
and preserves ambiguity when the model is vague (Phase 28).
"""
from __future__ import annotations

from typing import Any

_SCHEMA_VERSION = "llm_startup_understanding.v1"

_MAX_BRIEF = 4000
_MAX_RATIONALE = 2000
_MAX_LIST_STR = 16
_MAX_ARTIFACTS = 24
_MAX_LEDGER_ITEMS = 12
_MAX_BLOCKERS = 6
_MAX_FOCUS_CANDIDATES = 12
_MAX_ORIENTATION_NOTES = 2000

_GENERIC_IMPACT_TIERS = frozenset({"high", "medium", "low", "unknown"})


def work_item_impact_tier(row: dict[str, Any]) -> str:
    """Generic relative urgency: ``high`` | ``medium`` | ``low`` | ``unknown``.

    ``unknown`` means underspecified or domain-shaped tokens we do not interpret in shared code.
    """
    if not isinstance(row, dict):
        return "unknown"
    explicit = str(row.get("impact_tier") or "").strip().lower()
    if explicit in _GENERIC_IMPACT_TIERS:
        return explicit
    if row.get("importance") is not None:
        try:
            v = int(row["importance"])
            v = max(0, min(100, v))
            if v >= 67:
                return "high"
            if v >= 34:
                return "medium"
            return "low"
        except (TypeError, ValueError):
            pass
    imp_str = str(row.get("importance") or "").strip().lower()
    if imp_str in ("high", "h"):
        return "high"
    if imp_str in ("medium", "med", "m"):
        return "medium"
    if imp_str in ("low", "l"):
        return "low"
    mi = str(row.get("mission_impact") or "").strip().lower()
    if mi in ("high", "critical"):
        return "high"
    if mi == "medium":
        return "medium"
    if mi == "low":
        return "low"
    if mi in ("quality", "none"):
        return "low"
    # Any other mission_impact string (including legacy domain-shaped tokens) is not interpreted here.
    return "unknown"


def _normalize_candidate_work_item(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["impact_tier"] = work_item_impact_tier(row)
    sk = str(out.get("suggested_decision_key") or out.get("suggested_key") or "").strip().lower()[:64] or None
    if sk:
        out["suggested_decision_key"] = sk
    st = str(out.get("state") or "").strip().lower()
    if not st and out.get("status"):
        out["state"] = str(out.get("status")).strip().lower()[:32]
    return out


def _merge_ledger_rows(
    initial: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    max_rows: int,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in (initial, candidates):
        for raw in bucket:
            if not isinstance(raw, dict):
                continue
            norm = _normalize_candidate_work_item(raw)
            title = str(norm.get("title") or norm.get("label") or "").strip().lower()[:240]
            if title:
                if title in seen:
                    continue
                seen.add(title)
            merged.append(norm)
            if len(merged) >= max_rows:
                return merged
    return merged


def _merge_blocker_rows(
    initial: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    max_rows: int,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in (initial, candidates):
        for raw in bucket:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or raw.get("label") or "").strip().lower()[:240]
            if title:
                if title in seen:
                    continue
                seen.add(title)
            merged.append(raw)
            if len(merged) >= max_rows:
                return merged
    return merged


def _merge_focus_rows(
    initial: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    max_rows: int,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in (initial, candidates):
        for raw in bucket:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("decision_key") or raw.get("suggested_key") or raw.get("title") or "").strip().lower()[:200]
            if key:
                if key in seen:
                    continue
                seen.add(key)
            merged.append(raw)
            if len(merged) >= max_rows:
                return merged
    return merged


def startup_understanding_has_minimum_viable(coerced: dict[str, Any] | None) -> bool:
    """True when the startup document carries enough signal to accept an orient without other adapters."""
    if not isinstance(coerced, dict):
        return False
    if len(str(coerced.get("orientation_brief") or "").strip()) >= 20:
        return True
    if len(str(coerced.get("startup_rationale") or "").strip()) >= 20:
        return True
    if len(str(coerced.get("orientation_notes") or "").strip()) >= 20:
        return True
    if coerced.get("initial_ledger_items"):
        return True
    if coerced.get("initial_blockers"):
        return True
    if coerced.get("initial_uncertainties"):
        return True
    if coerced.get("initial_dependencies"):
        return True
    if coerced.get("artifact_inventory"):
        return True
    if coerced.get("initial_focus_candidates"):
        return True
    return False


def fallback_decision_key_for_startup_merge(
    *,
    orient_items: list[dict[str, Any]] | None,
    startup: dict[str, Any] | None,
) -> str | None:
    """Best-effort linkage hint for emergent blocker updates; not a harness ontology requirement."""
    for item in orient_items or []:
        if not isinstance(item, dict):
            continue
        k = str(item.get("key") or "").strip().lower()
        if k:
            return k
    if not isinstance(startup, dict):
        return None
    for row in list(startup.get("initial_ledger_items") or []):
        if not isinstance(row, dict):
            continue
        sk = str(row.get("suggested_key") or row.get("suggested_decision_key") or "").strip().lower()
        if sk:
            return sk[:64]
    for row in list(startup.get("initial_focus_candidates") or []):
        if not isinstance(row, dict):
            continue
        sk = str(row.get("decision_key") or row.get("suggested_key") or "").strip().lower()
        if sk:
            return sk[:64]
    return None


def coerce_startup_understanding(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Bounded, JSON-safe startup document from orient LLM output (partial OK)."""
    if not isinstance(raw, dict):
        raw = {}
    brief = str(raw.get("orientation_brief") or raw.get("brief") or "").strip()[:_MAX_BRIEF] or None
    rationale = str(raw.get("startup_rationale") or raw.get("rationale") or "").strip()[:_MAX_RATIONALE] or None
    notes = str(raw.get("orientation_notes") or "").strip()[:_MAX_ORIENTATION_NOTES] or None

    inv: list[str] = []
    for x in list(raw.get("initial_uncertainties") or [])[:_MAX_LIST_STR]:
        s = str(x).strip()
        if s:
            inv.append(s[:400])

    deps: list[str] = []
    for x in list(raw.get("initial_dependencies") or [])[:_MAX_LIST_STR]:
        s = str(x).strip()
        if s:
            deps.append(s[:400])
    for x in list(raw.get("candidate_dependencies") or [])[:_MAX_LIST_STR]:
        s = str(x).strip()
        if s and s not in deps:
            deps.append(s[:400])

    artifacts: list[dict[str, Any]] = []
    for a in list(raw.get("artifact_inventory") or [])[:_MAX_ARTIFACTS]:
        if not isinstance(a, dict):
            continue
        artifacts.append(
            {
                "ref": str(a.get("ref") or a.get("artifact_ref") or "").strip()[:400] or None,
                "label": str(a.get("label") or "").strip()[:240] or None,
                "kind": str(a.get("kind") or "").strip()[:64] or None,
                "note": str(a.get("note") or "").strip()[:400] or None,
            }
        )

    ledger_merged = _merge_ledger_rows(
        list(raw.get("initial_ledger_items") or [])[:_MAX_LEDGER_ITEMS],
        list(raw.get("candidate_work_items") or [])[:_MAX_LEDGER_ITEMS],
        max_rows=_MAX_LEDGER_ITEMS,
    )
    blockers_merged = _merge_blocker_rows(
        list(raw.get("initial_blockers") or [])[:_MAX_BLOCKERS],
        list(raw.get("candidate_blockers") or [])[:_MAX_BLOCKERS],
        max_rows=_MAX_BLOCKERS,
    )
    focus_merged = _merge_focus_rows(
        list(raw.get("initial_focus_candidates") or [])[:_MAX_FOCUS_CANDIDATES],
        list(raw.get("candidate_focus_candidates") or [])[:_MAX_FOCUS_CANDIDATES],
        max_rows=_MAX_FOCUS_CANDIDATES,
    )

    return {
        "schema_version": _SCHEMA_VERSION,
        "orientation_brief": brief,
        "startup_rationale": rationale,
        "orientation_notes": notes,
        "artifact_inventory": artifacts,
        "initial_uncertainties": inv,
        "initial_dependencies": deps,
        "initial_ledger_items": ledger_merged,
        "initial_blockers": blockers_merged,
        "initial_focus_candidates": focus_merged,
    }
