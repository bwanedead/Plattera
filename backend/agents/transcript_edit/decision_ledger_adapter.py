"""Transcript-edit adapter: legacy checklist store ↔ unified harness decision ledger.

``state.decision_ledger`` is the **transcript-edit-native persistence / mutation** store.
The **canonical organized-work read surface** is the unified envelope
(:func:`build_transcript_edit_unified_decision_ledger`) plus the derived
:func:`transcript_edit_closure_read_ledger` (items from the envelope; tickets and
completeness metadata from native).

Domain slot ordering for tie-breaks lives here—not in the generic harness ledger.
"""
from __future__ import annotations

from typing import Any

from harness.work_board.contracts import MAX_BOARD_CONTEXT_NOTES_PER_ITEM, new_work_board

# Loop state is referenced as a duck-typed object to avoid importing ``loop_state`` here.

from .decision_ledger_scope import _ensure_ledger_shape
from .transcript_edit_default_checklist_seed import TRANSCRIPT_EDIT_DEFAULT_SLOT_PRIORITY
from .work_board_projection import project_decision_ledger_to_work_board

# Re-export domain slot ordering (defined in default checklist seed module).
TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY: dict[str, int] = dict(TRANSCRIPT_EDIT_DEFAULT_SLOT_PRIORITY)

_NATIVE_LEDGER_TOP_LEVEL_KEYS = frozenset({
    "summary",
    "external_context_injections",
    "scope_summaries",
    "source_completeness",
    "source_completeness_reason",
    "source_limitations",
    "blocker_feedback_state",
})

_BOARD_TO_LEDGER_STATE: dict[str, str] = {
    "open": "unknown",
    "investigating": "candidate_found",
    "blocked": "disputed",
    "narrowed": "accepted_with_risk",
    "waiting_human": "candidate_found",
    "waiting_evidence": "candidate_found",
    "answered_pending_integration": "candidate_found",
    "resolved": "verified",
    "superseded": "verified",
}


def build_transcript_edit_unified_decision_ledger(
    *,
    decision_ledger: dict[str, Any],
    harness_emergent_board_items: list[dict[str, Any]] | None = None,
    harness_board_context_notes: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Single unified harness decision ledger envelope for transcript-edit (projection + emergent + notes)."""
    base = project_decision_ledger_to_work_board(decision_ledger)
    domain = str(base.get("domain_projection") or "transcript_edit.decision_ledger")
    notes = harness_board_context_notes or {}
    items_out: list[dict[str, Any]] = []

    def merge_notes(row: dict[str, Any]) -> dict[str, Any]:
        r = dict(row)
        iid = str(r.get("item_id") or "")
        extra = notes.get(iid) if iid else None
        if isinstance(extra, list) and extra:
            existing = [dict(x) for x in (r.get("context_notes") or []) if isinstance(x, dict)]
            merged = existing + [dict(x) for x in extra if isinstance(x, dict)]
            r["context_notes"] = merged[-MAX_BOARD_CONTEXT_NOTES_PER_ITEM:]
        elif "context_notes" not in r:
            r["context_notes"] = []
        return r

    for row in list(base.get("items") or []):
        if isinstance(row, dict):
            items_out.append(merge_notes(dict(row)))
    for em in harness_emergent_board_items or []:
        if isinstance(em, dict):
            items_out.append(merge_notes(dict(em)))
    return new_work_board(domain_projection=domain, items=items_out)


def legacy_decision_ledger_items_from_unified(unified: dict[str, Any]) -> list[dict[str, Any]]:
    """Reconstruct transcript-edit checklist-shaped items from unified ``te:ledger:*`` rows only."""
    out: list[dict[str, Any]] = []
    for row in list(unified.get("items") or []):
        if not isinstance(row, dict):
            continue
        iid = str(row.get("item_id") or "").strip()
        if not iid.startswith("te:ledger:"):
            continue
        suffix = iid.rsplit(":", 1)[-1].strip().lower()
        dp = row.get("domain_payload") if isinstance(row.get("domain_payload"), dict) else {}
        key = str(dp.get("decision_key") or suffix).strip().lower()
        if not key:
            continue
        bstate = str(row.get("state") or "open").strip().lower()
        ledger_state = _BOARD_TO_LEDGER_STATE.get(bstate, "unknown")
        impact = str(row.get("blocking_impact") or "").strip().lower()
        blocking = bool(dp.get("blocking_flag")) or impact == "mapping_blocking"
        cr = dp.get("closure_requirement") if isinstance(dp.get("closure_requirement"), dict) else {}
        cr_d = dict(cr) if cr else {}
        scope = row.get("scope") if isinstance(row.get("scope"), dict) else {}
        scope_id = str(scope.get("scope_id") or "unknown_scope").strip().lower()
        item: dict[str, Any] = {
            "key": key,
            "label": str(dp.get("ledger_label") or row.get("title") or key).strip(),
            "state": ledger_state,
            "selected_value": dp.get("selected_value"),
            "alternatives": list(row.get("alternatives") or [])[:16],
            "confidence": dp.get("confidence"),
            "blocking": blocking,
            "evidence_refs": list(row.get("evidence_refs") or [])[:24],
            "user_override_state": str(dp.get("user_override_state") or "none").strip() or "none",
            "layer_tag": str(dp.get("layer_tag") or scope.get("layer_tag") or "layer1_canonical_recovery").strip(),
            "operational_impact": (
                "mapping_blocking" if blocking or impact == "mapping_blocking" else "transcript_quality_only"
            ),
            "provenance": str(dp.get("provenance") or row.get("provenance") or "").strip() or None,
            "verification_required": bool(dp.get("verification_required")),
            "scope_id": scope_id,
            "scope_label": str(scope.get("scope_label") or "").strip() or None,
            "scope_priority": int(row.get("priority") or 50),
            "in_target_scope": scope.get("in_target_scope"),
            "scope_proof": [],
            "closure_requirement": cr_d if cr_d else None,
        }
        out.append(item)
    return out


def legacy_decision_ledger_shape_from_unified(unified: dict[str, Any]) -> dict[str, Any]:
    """Minimal ledger-shaped dict for closure/focus utilities derived from a unified envelope."""
    return {"items": legacy_decision_ledger_items_from_unified(unified)}


def transcript_edit_closure_read_ledger(
    *,
    unified_decision_ledger: dict[str, Any],
    native_decision_ledger: dict[str, Any] | None,
) -> dict[str, Any]:
    """Canonical **read** model for transcript-edit closure/registry/focus helpers.

    Checklist-shaped ``items`` are reconstructed from the unified envelope (``te:ledger:*``
    rows). Top-level fields that are not represented on the envelope (tickets, scope
    summaries, completeness) are copied from the native persistence dict.

    Writes remain on ``state.decision_ledger``; this view is derived only.
    """
    merged: dict[str, Any] = {"items": legacy_decision_ledger_items_from_unified(unified_decision_ledger)}
    native = native_decision_ledger if isinstance(native_decision_ledger, dict) else {}
    for k in _NATIVE_LEDGER_TOP_LEVEL_KEYS:
        if k in native:
            merged[k] = native[k]
    return _ensure_ledger_shape(merged)


def transcript_edit_unified_and_closure_read_for_native(
    *,
    native_decision_ledger: dict[str, Any],
    harness_emergent_board_items: list[dict[str, Any]] | None = None,
    harness_board_context_notes: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build unified envelope + closure read ledger from native persistence dict.

    Single entrypoint for transcript-edit **read** convergence (focus packet, repair,
    controller, domain pack). Callers should prefer this over ad-hoc
    ``build_*`` + ``transcript_edit_closure_read_ledger`` duplication.
    """
    unified = build_transcript_edit_unified_decision_ledger(
        decision_ledger=native_decision_ledger if isinstance(native_decision_ledger, dict) else {},
        harness_emergent_board_items=harness_emergent_board_items,
        harness_board_context_notes=harness_board_context_notes,
    )
    read = transcript_edit_closure_read_ledger(
        unified_decision_ledger=unified,
        native_decision_ledger=native_decision_ledger if isinstance(native_decision_ledger, dict) else None,
    )
    return unified, read


def transcript_edit_unified_and_closure_read_from_loop_state(state: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Same as :func:`transcript_edit_unified_and_closure_read_for_native` using loop state fields."""
    native = getattr(state, "decision_ledger", None)
    if not isinstance(native, dict):
        native = {}
    items = getattr(state, "harness_emergent_board_items", None)
    notes = getattr(state, "harness_board_context_notes", None)
    return transcript_edit_unified_and_closure_read_for_native(
        native_decision_ledger=native,
        harness_emergent_board_items=list(items) if isinstance(items, list) else None,
        harness_board_context_notes=dict(notes) if isinstance(notes, dict) else None,
    )
