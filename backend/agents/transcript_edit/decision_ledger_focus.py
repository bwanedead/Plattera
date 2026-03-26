"""Compatibility-only focus helpers for transcript-edit.

Live transcript-edit focus selection now flows through continuity-first runtime plumbing and the
shared ``mission_state`` / ``resolution_state`` model. This module remains for legacy callers and
tests that still need advisory ordering, ranking, or audit helpers during the transition.
"""
from __future__ import annotations

from typing import Any

from harness.decision_ledger import envelope_is_unified_decision_ledger

from .board_focus_shaping import (
    board_focus_sort_suffix,
    emergent_board_sort_suffix,
    ledger_discovery_focus_sort_suffix,
)
from .decision_ledger_adapter import (
    TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY,
    legacy_decision_ledger_shape_from_unified,
)
from .decision_ledger_closure import unresolved_mapping_blocking_requirements
from .decision_ledger_scope import (
    _ensure_ledger_shape,
    _normalize_scope_status,
    _scope_id_from_scope_status,
    _scope_label,
    _scope_rank,
)
from .organized_work_composition import compute_organized_work_composition
from .transcript_edit_discovery_lifecycle import discovery_lifecycle_priority_penalty
from .transcript_edit_ledger_discovery_prep import (
    DISCOVERY_ITEM_PROVENANCE,
    DISCOVERY_KEY_PREFIX,
    WEAK_SEED_SCAFFOLDING_PRIORITY_PENALTY,
    discovery_maturity_priority_bonus,
    is_weak_seed_scaffolding_row,
)
from .work_board_projection import (
    HARNESS_EMERGENT_ITEM_PREFIX,
    active_work_board_item_for_key,
    project_decision_ledger_to_work_board,
)
from .work_board_read import board_is_mapping_blocking

_UNRESOLVED_STATES = {"unknown", "candidate_found", "disputed", "accepted_with_risk"}


def resolve_focus_authority_mode(*, mapping_blocking_by_key: dict[str, Any]) -> str:
    """Compatibility helper for legacy advisory ordering snapshots."""
    return "ledger_absolute_precedence" if mapping_blocking_by_key else "emergent_may_lead"


def authority_rank_for_candidate(
    candidate: dict[str, Any],
    *,
    mapping_blocking_by_key: dict[str, Any],
) -> int:
    """Compatibility helper for legacy advisory candidate ordering."""
    mode = resolve_focus_authority_mode(mapping_blocking_by_key=mapping_blocking_by_key)
    src = str(candidate.get("_candidate_source") or "")
    key = str(candidate.get("key") or "").strip().lower()
    if src in {"ledger_decision", "ledger_discovery"}:
        mapped = mapping_blocking_by_key.get(key)
        if isinstance(mapped, dict) and bool(mapped.get("mapping_blocking")):
            return 0
        return 1
    if src == "harness_emergent":
        return 2 if mode == "ledger_absolute_precedence" else 0
    return 1


def focus_authority_audit(
    *,
    mapping_blocking_by_key: dict[str, Any],
    winner: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility-only snapshot for legacy advisory/debug surfaces."""
    mode = resolve_focus_authority_mode(mapping_blocking_by_key=mapping_blocking_by_key)
    n = len(mapping_blocking_by_key)
    note = (
        "Material ledger mapping-blocking closure rows exist; emergent board rows defer in advisory ordering."
        if mode == "ledger_absolute_precedence"
        else "No material ledger mapping-blocking closure rows; emergent board rows may lead advisory ordering."
    )
    out: dict[str, Any] = {
        "schema_version": "focus_authority.v1",
        "mode": mode,
        "material_mapping_blocker_key_count": n,
        "policy_summary": note[:320],
    }
    if isinstance(winner, dict) and winner:
        out["winner_authority_rank"] = authority_rank_for_candidate(
            winner,
            mapping_blocking_by_key=mapping_blocking_by_key,
        )
        out["winner_candidate_source"] = str(winner.get("_candidate_source") or "") or None
    return out


def _board_row_to_pseudo_ledger_state(board_state_raw: str) -> str:
    b = str(board_state_raw or "open").strip().lower()
    if b == "blocked":
        return "disputed"
    if b == "narrowed":
        return "accepted_with_risk"
    if b == "investigating":
        return "candidate_found"
    return "unknown"


def _harness_emergent_focus_candidates(
    unified_decision_ledger: dict[str, Any] | None,
    *,
    ledger_candidate_keys: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(unified_decision_ledger, dict):
        return []
    out: list[dict[str, Any]] = []
    for row in list(unified_decision_ledger.get("items") or []):
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("item_id") or "").strip()
        if not item_id.startswith(HARNESS_EMERGENT_ITEM_PREFIX):
            continue
        bstate = str(row.get("state") or "open").strip().lower()
        if bstate in {"resolved", "superseded"}:
            continue
        dp = row.get("domain_payload") if isinstance(row.get("domain_payload"), dict) else {}
        link = str(dp.get("decision_key") or "").strip().lower()
        if link and link in ledger_candidate_keys:
            continue
        pseudo_state = _board_row_to_pseudo_ledger_state(bstate)
        blocking = bool(board_is_mapping_blocking(row) or str(row.get("materiality") or "").strip().lower() == "high")
        scope = row.get("scope") if isinstance(row.get("scope"), dict) else {}
        scope_id_raw = str(scope.get("scope_id") or "unknown_scope").strip().lower()
        if scope_id_raw not in {"target_scope", "outside_target_scope", "unknown_scope"}:
            scope_id_raw = "unknown_scope"
        scope_priority = _scope_rank(scope_id_raw)
        out.append(
            {
                "key": item_id,
                "label": str(row.get("title") or item_id).strip()[:240] or item_id,
                "state": pseudo_state,
                "blocking": blocking,
                "alternatives": list(row.get("alternatives") or [])[:16],
                "priority": int(row.get("priority") or 50),
                "effective_focus_priority": int(row.get("priority") or 50),
                "evidence_count": len(list(row.get("evidence_refs") or [])),
                "block_reason": "",
                "contradiction_rank": 0,
                "scope_id": scope_id_raw,
                "scope_label": _scope_label(scope_id_raw),
                "scope_priority": scope_priority,
                "_ledger_item": {},
                "_candidate_source": "harness_emergent",
                "_harness_emergent_row": dict(row),
            }
        )
    return out


def choose_investigation_focus(
    ledger: dict[str, Any] | None = None,
    *,
    work_board: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Compatibility-only focus ordering from the unified harness decision ledger envelope.

    Transitional call shapes (all equivalent when data is consistent):

    - ``ledger`` = transcript-edit native store, ``work_board`` = unified envelope (preferred during migration).
    - ``ledger`` only: unified envelope is ``project_decision_ledger_to_work_board(ledger)`` (no emergent rows).
    - ``ledger`` = unified envelope (``work_board.v1``): closure rows are reconstructed from ``te:ledger:*`` items.
    - ``work_board`` only: pass ``ledger=None``; closure reconstructed from the envelope.

    The result is advisory context for legacy surfaces. Live runtime should treat continuity,
    feedback, and emergent blockers as the active-item truth source instead.
    """
    if work_board is not None:
        unified = work_board
        closure_source: dict[str, Any]
        if ledger is not None:
            closure_source = ledger
        else:
            closure_source = legacy_decision_ledger_shape_from_unified(unified)
    elif ledger is not None and envelope_is_unified_decision_ledger(ledger):
        unified = ledger
        closure_source = legacy_decision_ledger_shape_from_unified(unified)
    elif ledger is not None:
        unified = project_decision_ledger_to_work_board(ledger)
        closure_source = ledger
    else:
        return None

    normalized = _ensure_ledger_shape(closure_source)
    candidates: list[dict[str, Any]] = []
    mapping_blocking_by_key = {
        str(item.get("key") or ""): item
        for item in unresolved_mapping_blocking_requirements(normalized)
        if isinstance(item, dict)
    }
    has_unresolved_discovery = False
    for _it in normalized["items"]:
        if not isinstance(_it, dict):
            continue
        if str(_it.get("state") or "") not in _UNRESOLVED_STATES:
            continue
        if str(_it.get("key") or "").startswith(DISCOVERY_KEY_PREFIX):
            has_unresolved_discovery = True
            break
        if str(_it.get("provenance") or "").strip() == DISCOVERY_ITEM_PROVENANCE:
            has_unresolved_discovery = True
            break
    seed_awake_unresolved = 0
    for _it in normalized["items"]:
        if not isinstance(_it, dict):
            continue
        if str(_it.get("state") or "") not in _UNRESOLVED_STATES:
            continue
        k0 = str(_it.get("key") or "")
        prov0 = str(_it.get("provenance") or "").strip()
        is_disc0 = prov0 == DISCOVERY_ITEM_PROVENANCE or k0.startswith(DISCOVERY_KEY_PREFIX)
        if is_disc0:
            continue
        if _it.get("seed_scaffolding_dormant") is not True:
            seed_awake_unresolved += 1
    for item in normalized["items"]:
        if not isinstance(item, dict):
            continue
        state = str(item.get("state") or "unknown")
        if state not in _UNRESOLVED_STATES:
            continue
        key = str(item.get("key") or "")
        prov = str(item.get("provenance") or "").strip()
        is_discovery = prov == DISCOVERY_ITEM_PROVENANCE or str(key).startswith(DISCOVERY_KEY_PREFIX)
        if (
            not is_discovery
            and item.get("seed_scaffolding_dormant") is True
            and has_unresolved_discovery
            and prov.lower() in ("deterministic", "")
        ):
            # Phase 14: dormant bootstrap slots stay out of focus while discovery defines active work.
            continue
        requirement = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
        mapped_item = mapping_blocking_by_key.get(key)
        blocking = bool((mapped_item or {}).get("mapping_blocking")) if isinstance(mapped_item, dict) else bool(item.get("blocking"))
        if mapped_item is None and blocking and not is_discovery:
            # Prefer materially mapped blockers first; unknown placeholders come after.
            # Discovery-first rows are not seed placeholders; keep their blocking flag.
            blocking = False
        scope_status = _normalize_scope_status(requirement.get("scope_status"))
        scope_id = _scope_id_from_scope_status(scope_status)
        scope_priority = _scope_rank(scope_id)
        block_reason = str(requirement.get("block_reason") or "").strip().lower()
        contradiction_rank = 1 if block_reason == "contradiction" else 0
        cand_source = "ledger_discovery" if is_discovery else "ledger_decision"
        dm = item.get("discovery_meta") if isinstance(item.get("discovery_meta"), dict) else {}
        weak_seed = is_weak_seed_scaffolding_row(item=item, contradiction_rank=contradiction_rank)
        if is_discovery:
            try:
                slot_priority = int(item.get("scope_priority") or 42)
            except (TypeError, ValueError):
                slot_priority = 42
            mat_bonus = discovery_maturity_priority_bonus(dm)
            lc_pen = discovery_lifecycle_priority_penalty(dm)
            effective_focus_priority = int(slot_priority) - int(mat_bonus) + int(lc_pen)
        else:
            slot_priority = TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY.get(key, 99)
            penalty = WEAK_SEED_SCAFFOLDING_PRIORITY_PENALTY if weak_seed else 0
            effective_focus_priority = int(slot_priority) + int(penalty)
        candidates.append(
            {
                "key": key,
                "label": str(item.get("label") or key or "decision"),
                "state": state,
                "blocking": blocking,
                "alternatives": list(item.get("alternatives") or []),
                "priority": slot_priority,
                "effective_focus_priority": effective_focus_priority,
                "evidence_count": len(list(item.get("evidence_refs") or [])),
                "block_reason": block_reason,
                "contradiction_rank": contradiction_rank,
                "scope_id": scope_id,
                "scope_label": _scope_label(scope_id),
                "scope_priority": scope_priority,
                "_ledger_item": dict(item),
                "_candidate_source": cand_source,
                "_weak_seed_scaffolding": weak_seed,
            }
        )
    ledger_candidate_keys = {str(c.get("key") or "").strip().lower() for c in candidates if str(c.get("key") or "").strip()}
    candidates.extend(_harness_emergent_focus_candidates(unified, ledger_candidate_keys=ledger_candidate_keys))
    if not candidates:
        return None

    def sort_key(c: dict[str, Any]) -> tuple[Any, ...]:
        if str(c.get("_candidate_source") or "") == "harness_emergent":
            row_h = c.get("_harness_emergent_row") if isinstance(c.get("_harness_emergent_row"), dict) else {}
            suffix = emergent_board_sort_suffix(row_h)
        else:
            board_item = (
                active_work_board_item_for_key(unified, str(c.get("key") or ""))
                if isinstance(unified, dict)
                else None
            )
            li = c.get("_ledger_item") if isinstance(c.get("_ledger_item"), dict) else {}
            if str(c.get("_candidate_source") or "") == "ledger_discovery":
                suffix = ledger_discovery_focus_sort_suffix(li, board_item)
            else:
                suffix = board_focus_sort_suffix(
                    str(c.get("key") or ""),
                    li,
                    board_item,
                )
        authority_rank = authority_rank_for_candidate(c, mapping_blocking_by_key=mapping_blocking_by_key)
        return (
            int(authority_rank),
            0 if c["blocking"] else 1,
            int(c["scope_priority"]),
            -int(c["contradiction_rank"]),
            -_uncertainty_rank(str(c["state"])),
            int(c.get("effective_focus_priority", c["priority"])),
            -int(c["evidence_count"]),
        ) + suffix

    candidates.sort(key=sort_key)
    winner = candidates[0]
    reason_code, reason_text = _focus_reason_for_candidate(winner)
    comp = compute_organized_work_composition(
        native_decision_ledger=closure_source,
        unified_work_board=unified,
    )
    advisory_candidates = [
        _public_candidate_view(c)
        for c in candidates[:5]
    ]
    seed_candidate = _public_candidate_view(
        winner,
        reason_code=reason_code,
        reason_text=reason_text,
    )
    out = {
        "seed_candidate": seed_candidate,
        "seed_source": str(winner.get("_candidate_source") or "").strip() or None,
        # Transitional aliases for current callers/tests; advisory_candidates is the primary surface.
        "decision_key": seed_candidate.get("decision_key"),
        "decision_label": seed_candidate.get("label"),
        "state": seed_candidate.get("state"),
        "blocking": seed_candidate.get("blocking"),
        "scope_id": seed_candidate.get("scope_id"),
        "scope_label": seed_candidate.get("scope_label"),
        "scope_priority": seed_candidate.get("scope_priority"),
        "in_target_scope": seed_candidate.get("in_target_scope"),
        "next_check_reason_code": seed_candidate.get("next_check_reason_code"),
        "next_check_reason": seed_candidate.get("next_check_reason"),
        "focus_target_kind": seed_candidate.get("focus_target_kind"),
        "focus_authority": focus_authority_audit(
            mapping_blocking_by_key=mapping_blocking_by_key,
            winner=winner,
        ),
        "organized_work_composition": comp,
        "advisory_candidates": advisory_candidates,
        "bootstrap_focus_source": str(winner.get("_candidate_source") or "").strip() or None,
    }
    return out


def has_blocking_dispute(ledger: dict[str, Any] | None) -> bool:
    normalized = _ensure_ledger_shape(ledger)
    for item in normalized["items"]:
        if not isinstance(item, dict):
            continue
        if bool(item.get("blocking")) and str(item.get("state") or "") == "disputed":
            alternatives = [str(v).strip() for v in list(item.get("alternatives") or []) if str(v).strip()]
            if len(alternatives) > 1:
                return True
    return False


def _uncertainty_rank(state: str) -> int:
    if state == "disputed":
        return 4
    if state == "unknown":
        return 3
    if state == "accepted_with_risk":
        return 2
    if state == "candidate_found":
        return 1
    return 0


def _focus_reason_for_candidate(candidate: dict[str, Any]) -> tuple[str, str]:
    if str(candidate.get("_candidate_source") or "") == "harness_emergent":
        label = str(candidate.get("label") or "harness work item").strip()
        return (
            "harness_emergent_board_item",
            f"Prioritizing durable harness-emergent decision-ledger item: {label}.",
        )
    if str(candidate.get("_candidate_source") or "") == "ledger_discovery":
        label = str(candidate.get("label") or "discovered work item").strip()
        return ("ledger_discovery_item", f"Prioritizing discovery-first ledger item: {label}.")
    state = str(candidate.get("state") or "unknown")
    label = str(candidate.get("label") or "mapping-critical detail")
    blocking = bool(candidate.get("blocking"))
    alternatives = [str(v).strip() for v in list(candidate.get("alternatives") or []) if str(v).strip()]
    if blocking and state == "disputed" and len(alternatives) > 1:
        return ("blocking_conflict_unresolved", f"Prioritizing {label}: blocking conflict remains unresolved.")
    if blocking and state in {"unknown", "candidate_found", "accepted_with_risk"}:
        return ("blocking_mapping_critical", f"Prioritizing {label}: mapping-critical evidence is still incomplete.")
    if state == "disputed":
        return ("highest_uncertainty", f"Prioritizing {label}: it has the highest unresolved uncertainty.")
    return ("next_open_item", f"Prioritizing {label}: it is the next unresolved checklist item.")


def _public_candidate_view(
    candidate: dict[str, Any],
    *,
    reason_code: str | None = None,
    reason_text: str | None = None,
) -> dict[str, Any]:
    key = str(candidate.get("key") or "").strip().lower() or None
    label = str(candidate.get("label") or "").strip() or None
    scope_id = str(candidate.get("scope_id") or "").strip() or None
    target_kind = (
        "harness_emergent"
        if str(candidate.get("_candidate_source") or "") == "harness_emergent"
        else (
            "ledger_discovery"
            if str(candidate.get("_candidate_source") or "") == "ledger_discovery"
            else "ledger_decision"
        )
    )
    out = {
        "decision_key": key,
        "label": label,
        "focus_target_kind": target_kind,
        "state": str(candidate.get("state") or "").strip().lower() or None,
        "blocking": bool(candidate.get("blocking")),
        "scope_id": scope_id,
        "scope_label": str(candidate.get("scope_label") or "").strip() or None,
        "scope_priority": int(candidate.get("scope_priority") or 99),
        "in_target_scope": scope_id == "target_scope",
    }
    if reason_code:
        out["next_check_reason_code"] = reason_code
    if reason_text:
        out["next_check_reason"] = reason_text
    return out
