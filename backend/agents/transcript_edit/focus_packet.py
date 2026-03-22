"""Focus packet assembly for transcript-edit (model-facing bundles).

The unified **harness decision ledger** envelope is the organized-work read surface. The packet field
historically named ``work_board`` holds that envelope (``work_board.v1`` wire shape = decision ledger wire shape).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from harness.work_board.recent_iteration_lane import build_recent_iteration_lane

from .focus_packet_board_context import build_work_board_focus_context_bundle
from .focus_runtime import (
    baseline_residual_from_unresolved,
    next_recommended_action_text,
    recent_image_evidence_attempt_count,
)
from .decision_ledger_adapter import transcript_edit_unified_and_closure_read_for_native
from .organized_work_composition import compute_organized_work_composition
from .transcript_edit_ledger_discovery_prep import DISCOVERY_ITEM_PROVENANCE, DISCOVERY_KEY_PREFIX
from .work_board_projection import active_work_board_item_for_focus
from .work_board_read import (
    generic_knowns_snapshot,
    ledger_board_parity,
    board_is_mapping_blocking,
    board_materiality,
    board_state,
)

MAX_SPAN_COUNT = 6
MAX_SPAN_TEXT_CHARS = 320
MAX_IMAGE_RESULTS = 8
MAX_IMAGE_OBSERVED_TEXT_CHARS = 180
MAX_RECENT_ATTEMPTS = 6
MAX_ATTEMPT_REASON_CHARS = 120
MAX_FEEDBACK_VALUE_CHARS = 160
MAX_FEEDBACK_NOTE_CHARS = 240
MAX_MEMORY_SUMMARY_CHARS = 420
MAX_EXTERNAL_CONTEXT_INJECTIONS = 6
MAX_EXTERNAL_PAYLOAD_CHARS = 320


def build_focus_packet(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str | None,
    focus_source: str | None = None,
    focus_reason_code: str | None = None,
    loop_iteration: int | None = None,
    active_emergent_blocker: dict[str, Any] | None = None,
    blocker_registry: dict[str, Any] | None = None,
    source_transcript_ref: str | None,
    source_transcript_hash: str,
    span_context: list[dict[str, Any]],
    image_verification_payload: dict[str, Any],
    feedback: dict[str, Any] | None,
    continuity_log: list[dict[str, Any]] | None,
    visual_evidence_state: dict[str, Any] | None = None,
    seed_transcript_ref: str | None = None,
    edit_lineage_summary: list[dict[str, Any]] | None = None,
    t0_candidate_refs: list[str] | None = None,
    evidence_repeat_guard: dict[str, dict[str, Any]] | None = None,
    evidence_signal_counter: int = 0,
    harness_emergent_board_items: list[dict[str, Any]] | None = None,
    harness_board_context_notes: dict[str, list[dict[str, Any]]] | None = None,
    audit_evidence_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = str(decision_key or "").strip().lower()
    # Unified envelope + closure read model (single adapter entrypoint).
    work_board, read_ledger = transcript_edit_unified_and_closure_read_for_native(
        native_decision_ledger=decision_ledger if isinstance(decision_ledger, dict) else {},
        harness_emergent_board_items=harness_emergent_board_items,
        harness_board_context_notes=harness_board_context_notes,
    )
    active_work_item_lookup = active_work_board_item_for_focus(work_board, key) if key else None
    is_emergent_focus = bool(
        (key.startswith("harness:emergent:") if key else False)
        or (
            isinstance(active_work_item_lookup, dict)
            and str(active_work_item_lookup.get("provenance") or "").strip() == "harness.emergent.v1"
        )
    )
    if is_emergent_focus and isinstance(active_work_item_lookup, dict):
        ledger_item = _synthetic_ledger_item_from_emergent_board_row(active_work_item_lookup, key)
        closure_requirement = dict(ledger_item.get("closure_requirement") or {})
        ledger_row_for_parity = ledger_item
    else:
        li = _ledger_item_for_key(decision_ledger=read_ledger, decision_key=key)
        ledger_item = dict(li) if isinstance(li, dict) else {}
        closure_requirement = (
            dict(ledger_item.get("closure_requirement"))
            if isinstance(ledger_item.get("closure_requirement"), dict)
            else {}
        )
        ledger_row_for_parity = li if isinstance(li, dict) else None
    is_discovery_focus = bool(
        not is_emergent_focus
        and (
            (key.startswith(DISCOVERY_KEY_PREFIX) if key else False)
            or str((ledger_item or {}).get("provenance") or "").strip() == DISCOVERY_ITEM_PROVENANCE
        )
    )
    attempts = _recent_attempts_for_key(
        continuity_log=continuity_log or [],
        decision_key=key,
        max_items=MAX_RECENT_ATTEMPTS,
    )
    bounded_spans = _bounded_span_context(span_context)
    bounded_image = _bounded_image_verification(image_verification_payload=image_verification_payload, decision_key=key)
    bounded_visual = _bounded_visual_evidence(visual_evidence_state=visual_evidence_state, decision_key=key)
    bounded_feedback = _bounded_feedback(feedback=feedback, decision_key=key)
    external_injections = _bounded_external_context_injections(
        decision_ledger=read_ledger,
        decision_key=key,
    )
    scope_summaries = (
        dict(read_ledger.get("scope_summaries"))
        if isinstance(read_ledger.get("scope_summaries"), dict)
        else {}
    )
    blocker_feedback_state = (
        dict((blocker_registry or {}).get("counts"))
        if isinstance(blocker_registry, dict) and isinstance((blocker_registry or {}).get("counts"), dict)
        else (
            dict(read_ledger.get("blocker_feedback_state"))
            if isinstance(read_ledger.get("blocker_feedback_state"), dict)
            else {}
        )
    )
    blocker_registry_view = (
        {
            "active_blocker_id": str(blocker_registry.get("active_blocker_id") or "").strip() or None,
            "counts": dict(blocker_registry.get("counts") or {}),
            "convention_context": dict(blocker_registry.get("convention_context") or {}),
            "archetype_menu": {
                "menu_family_candidates": [
                    str(value)
                    for value in list((blocker_registry.get("archetype_menu") or {}).get("menu_family_candidates") or [])
                    if str(value).strip()
                ][:10],
                "archetypes": [
                    dict(row)
                    for row in list((blocker_registry.get("archetype_menu") or {}).get("archetypes") or [])
                    if isinstance(row, dict)
                ][:20],
            },
            "emergent": {
                "active_blocker_id": str(((blocker_registry.get("emergent") or {}).get("active_blocker_id") or "")).strip() or None,
                "counts": dict((blocker_registry.get("emergent") or {}).get("counts") or {}),
                "rows": [
                    dict(row)
                    for row in list((blocker_registry.get("emergent") or {}).get("rows") or [])
                    if isinstance(row, dict)
                ][:12],
            },
            "rows": [
                dict(row)
                for row in list(blocker_registry.get("rows") or [])
                if isinstance(row, dict)
            ][:12],
        }
        if isinstance(blocker_registry, dict)
        else {}
    )
    focused_blocker_pair = _focused_blocker_pair(
        blocker_feedback_state=blocker_feedback_state,
        decision_key=key,
    )
    if focused_blocker_pair is None:
        focused_blocker_pair = _focused_blocker_pair_fallback(
            decision_key=key,
            ledger_item=ledger_item or {},
            closure_requirement=closure_requirement,
            external_injections=external_injections,
    )
    emergent_focus = dict(active_emergent_blocker) if isinstance(active_emergent_blocker, dict) else {}
    active_work_item = active_work_item_lookup
    parity = ledger_board_parity(key, ledger_row_for_parity, active_work_item)
    investigation_brief = _investigation_brief(
        decision_key=key,
        ledger_item=ledger_item or {},
        closure_requirement=closure_requirement,
        recent_attempts=attempts,
        memory_summary=_memory_summary(attempts),
        source_completeness=str(read_ledger.get("source_completeness") or "unknown"),
        board_item=active_work_item,
    )
    working_plan = _working_plan(
        decision_key=key,
        focus_source=str(focus_source or "legacy_fallback").strip().lower() or "legacy_fallback",
        ledger_item=ledger_item or {},
        closure_requirement=closure_requirement,
        recent_attempts=attempts,
        investigation_brief=investigation_brief,
        active_emergent_blocker=emergent_focus,
        source_completeness=str(read_ledger.get("source_completeness") or "unknown"),
        board_item=active_work_item,
    )
    policy_signals = _derived_policy_signals(
        decision_key=key,
        ledger_item=ledger_item or {},
        closure_requirement=closure_requirement,
        recent_attempts=attempts,
        investigation_brief=investigation_brief,
        span_context=bounded_spans,
        image_verification=bounded_image,
        visual_evidence=bounded_visual,
        feedback=bounded_feedback,
        source_completeness=str(read_ledger.get("source_completeness") or "unknown"),
        evidence_repeat_guard=evidence_repeat_guard or {},
        evidence_signal_counter=evidence_signal_counter,
        board_item=active_work_item,
    )
    _lsu = (
        dict(decision_ledger.get("llm_startup_understanding"))
        if isinstance(decision_ledger, dict) and isinstance(decision_ledger.get("llm_startup_understanding"), dict)
        else {}
    )
    _liu = (
        dict(decision_ledger.get("llm_iteration_understanding"))
        if isinstance(decision_ledger, dict) and isinstance(decision_ledger.get("llm_iteration_understanding"), dict)
        else {}
    )
    support_state = {
        "investigation_brief": investigation_brief,
        "working_plan": working_plan,
        "policy_signals": policy_signals,
        "llm_startup_understanding": _lsu if _lsu else None,
        "llm_iteration_understanding": _liu if _liu else None,
        "audit_evidence_snapshot": audit_evidence_snapshot if isinstance(audit_evidence_snapshot, dict) else None,
    }
    recent_iteration_lane = build_recent_iteration_lane(
        continuity_log or [],
        current_iteration=loop_iteration,
    )
    focus_sel = {
        "decision_key": key or None,
        "focus_source": str(focus_source or "legacy_fallback").strip().lower() or "legacy_fallback",
        "focus_reason_code": str(focus_reason_code or "").strip()[:120] or None,
        "why_active_now": (
            f"Focus resolver selected {key} via "
            f"{str(focus_source or 'legacy_fallback').strip().lower() or 'legacy_fallback'} "
            f"({str(focus_reason_code or 'unspecified').strip()[:80]})."
            if key
            else None
        ),
    }
    blocker_posture = {
        "active_emergent_blocker_id": str(emergent_focus.get("blocker_id") or "").strip() or None,
        "understanding_strength": str(policy_signals.get("understanding_strength") or ""),
        "repair_eligible": bool(policy_signals.get("repair_eligible")),
        "escalation_eligible": bool(policy_signals.get("escalation_eligible")),
        "repeat_without_signal": bool(policy_signals.get("repeat_without_signal")),
    }
    if is_emergent_focus:
        ft_kind = "harness_emergent"
    elif is_discovery_focus:
        ft_kind = "ledger_discovery"
    else:
        ft_kind = "ledger_decision"
    dm0 = (
        ledger_item.get("discovery_meta")
        if isinstance(ledger_item, dict) and isinstance(ledger_item.get("discovery_meta"), dict)
        else {}
    )
    discovery_work_context: dict[str, Any] | None = None
    if is_discovery_focus and isinstance(ledger_item, dict):
        lme = dm0.get("last_merged_epoch")
        try:
            lme_i = int(lme) if lme is not None else None
        except (TypeError, ValueError):
            lme_i = None
        discovery_work_context = {
            "origin": "transcript_edit_discovery",
            "kind": str(dm0.get("kind") or "").strip()[:64] or None,
            "posture": str(dm0.get("posture") or "").strip()[:32] or None,
            "lifecycle_hint": str(dm0.get("lifecycle_hint") or "").strip()[:16] or None,
            "evidence_touch_count": int(dm0.get("evidence_touch_count") or 0),
            "signal_fp": str(dm0.get("signal_fp") or "").strip()[:32] or None,
            "last_merged_epoch": lme_i,
            "why_matters": str((closure_requirement or {}).get("required_information") or "").strip()[:240] or None,
        }
    work_board_focus_context = build_work_board_focus_context_bundle(
        decision_key=key,
        focus_target_kind=ft_kind,
        active_work_item=dict(active_work_item) if isinstance(active_work_item, dict) else None,
        work_board=work_board,
        decision_ledger=read_ledger,
        now_epoch=int(time.time()),
    )
    organized_work_composition = compute_organized_work_composition(
        native_decision_ledger=read_ledger,
        unified_work_board=work_board,
    )
    execution_context = {
        "schema_version": "execution_context.v1",
        "parity": parity,
        "focus_selection": focus_sel,
        "active_work_item": dict(active_work_item) if isinstance(active_work_item, dict) else None,
        "recent_iterations": recent_iteration_lane,
        "blocker_posture": blocker_posture,
        "support_state": support_state,
        "work_board_focus_context": work_board_focus_context,
        "discovery_work_context": discovery_work_context,
        "organized_work_composition": organized_work_composition,
        "organized_work_note": (
            "Unified harness decision ledger envelope (packet field `work_board`) is the organized-work surface — "
            "not the native JSON store. Native startup is discovery-first; optional checklist template is explicit. "
            "Templates materialize on audit/image/orient/evidence touch. Discovery rows can cool down when stale."
        ),
    }
    return {
        "focus_source": str(focus_source or "legacy_fallback").strip().lower() or "legacy_fallback",
        "focus_reason_code": str(focus_reason_code or "").strip()[:120] or None,
        "loop_iteration": loop_iteration,
        # Unified decision ledger envelope (work_board.v1 wire — historical field name `work_board`).
        "work_board": work_board,
        "recent_iteration_lane": recent_iteration_lane,
        "execution_context": execution_context,
        "decision_key": key,
        "investigation_brief": investigation_brief,
        "working_plan": working_plan,
        "policy_signals": policy_signals,
        "support_state": support_state,
        "active_emergent_blocker": (
            {
                "blocker_id": str(emergent_focus.get("blocker_id") or "").strip() or None,
                "blocker_kind": str(emergent_focus.get("blocker_kind") or "").strip().lower() or None,
                "title": str(emergent_focus.get("title") or "").strip() or None,
                "blocking_class": str(emergent_focus.get("blocking_class") or "").strip().lower() or None,
                "reason": str(emergent_focus.get("reason") or "").strip() or None,
                "evidence_summary": str(emergent_focus.get("evidence_summary") or "").strip() or None,
                "candidate_values": [
                    str(value).strip()
                    for value in list(emergent_focus.get("candidate_values") or [])
                    if str(value).strip()
                ][:8],
                "resolution_condition": str(emergent_focus.get("resolution_condition") or "").strip() or None,
                "next_valid_actions": [
                    str(value).strip().lower()
                    for value in list(emergent_focus.get("next_valid_actions") or [])
                    if str(value).strip()
                ][:8],
                "scope_status": str(emergent_focus.get("scope_status") or "").strip().lower() or None,
            }
            if emergent_focus
            else None
        ),
        "ledger_item": ledger_item or {},
        "closure_requirement": closure_requirement,
        "scope_context": {
            "scope_id": str((ledger_item or {}).get("scope_id") or "unknown_scope"),
            "scope_label": str((ledger_item or {}).get("scope_label") or "Unknown Scope"),
            "scope_priority": int((ledger_item or {}).get("scope_priority") or 50),
            "in_target_scope": _tri_state_in_target_scope(
                (ledger_item or {}).get("in_target_scope"),
                str((closure_requirement or {}).get("scope_status") or "unknown"),
            ),
            "scope_status": str((closure_requirement or {}).get("scope_status") or "unknown"),
            "scope_proof": [
                str(v)
                for v in list((closure_requirement or {}).get("scope_proof") or [])
                if str(v).strip()
            ][:6],
            "target_scope_status": str((scope_summaries.get("target_scope") or {}).get("scope_closure_state") or "not_attempted"),
            "outside_target_scope_status": str((scope_summaries.get("outside_target_scope") or {}).get("scope_closure_state") or "not_attempted"),
        },
        "source_completeness": str(read_ledger.get("source_completeness") or "unknown"),
        "source_completeness_reason": (
            str(read_ledger.get("source_completeness_reason") or "").strip() or None
        ),
        "source_limitations": [
            str(v)
            for v in list(read_ledger.get("source_limitations") or [])
            if str(v).strip()
        ][:6],
        "source_transcript_ref": source_transcript_ref,
        "source_transcript_hash": source_transcript_hash,
        "span_context": bounded_spans,
        "image_verification": bounded_image,
        "visual_evidence": bounded_visual,
        "feedback": bounded_feedback,
        "external_context_injections": external_injections,
        "blocker_feedback_state": blocker_feedback_state,
        "blocker_registry": blocker_registry_view,
        "focused_blocker_feedback_pair": focused_blocker_pair,
        "recent_attempts": attempts,
        "memory_summary": _memory_summary(attempts),
        # D2 — edit lineage
        "seed_transcript_ref": seed_transcript_ref,
        "working_transcript_ref": source_transcript_ref,
        "edit_lineage": [dict(e) for e in (edit_lineage_summary or [])][-8:],
        # D1 — T0 consensus lane (populated when item is disputed + mapping-blocking)
        "t0_consensus": _build_t0_consensus(
            decision_key=key,
            ledger_item=ledger_item,
            closure_requirement=closure_requirement,
            t0_candidate_refs=t0_candidate_refs or [],
        ),
        "focus_target_kind": ft_kind,
        "active_emergent_board_item": (
            dict(active_work_item) if is_emergent_focus and isinstance(active_work_item, dict) else None
        ),
    }


def _board_item_state_to_ledger_like_state(raw: str) -> str:
    b = str(raw or "open").strip().lower()
    if b == "blocked":
        return "disputed"
    if b == "narrowed":
        return "accepted_with_risk"
    if b == "investigating":
        return "candidate_found"
    return "unknown"


def _synthetic_ledger_item_from_emergent_board_row(row: dict[str, Any], focus_key: str) -> dict[str, Any]:
    mb = board_is_mapping_blocking(row)
    st = _board_item_state_to_ledger_like_state(str(row.get("state") or ""))
    return {
        "key": focus_key,
        "state": st,
        "blocking": mb,
        "label": str(row.get("title") or "").strip()[:240] or None,
        "alternatives": list(row.get("alternatives") or [])[:16],
        "evidence_refs": list(row.get("evidence_refs") or [])[:24],
        "closure_requirement": {
            "mapping_blocking": mb,
            "operational_impact": "mapping_blocking" if mb else "transcript_quality_only",
            "required_information": str(row.get("resolution_condition") or "").strip()[:400] or None,
            "scope_status": "unknown",
        },
    }


def _ledger_item_for_key(*, decision_ledger: dict[str, Any], decision_key: str) -> dict[str, Any] | None:
    if not decision_key:
        return None
    items = decision_ledger.get("items") if isinstance(decision_ledger, dict) else []
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("key") or "").strip().lower() == decision_key:
            return dict(item)
    return None


def _recent_attempts_for_key(
    *,
    continuity_log: list[dict[str, Any]],
    decision_key: str,
    max_items: int,
) -> list[dict[str, Any]]:
    if not decision_key:
        return []
    matched: list[dict[str, Any]] = []
    for entry in continuity_log:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("decision_key") or "").strip().lower() != decision_key:
            continue
        matched.append(
            {
                "decision_key": decision_key,
                "move": str(entry.get("move") or "").strip()[:40],
                "outcome": str(entry.get("outcome") or "").strip()[:MAX_ATTEMPT_REASON_CHARS],
                "evidence_kind": str(entry.get("evidence_kind") or "").strip()[:40] or None,
                "state_delta_hint": str(entry.get("state_delta_hint") or "").strip()[:100] or None,
                "next_open_move_hint": str(entry.get("next_open_move_hint") or "").strip()[:100] or None,
            }
        )
    return matched[-max_items:]


def _memory_summary(recent_attempts: list[dict[str, Any]]) -> str:
    if not recent_attempts:
        return "No recent attempts recorded for this focus item."
    latest = recent_attempts[-1]
    move = str(latest.get("move") or "unknown_move")
    outcome = str(latest.get("outcome") or "unknown_outcome")
    summary = f"Recent focus history: last move={move}, outcome={outcome}, total_recent={len(recent_attempts)}."
    return summary[:MAX_MEMORY_SUMMARY_CHARS]


def _investigation_brief(
    *,
    decision_key: str,
    ledger_item: dict[str, Any],
    closure_requirement: dict[str, Any],
    recent_attempts: list[dict[str, Any]],
    memory_summary: str,
    source_completeness: str,
    board_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    residual = baseline_residual_from_unresolved(ledger_item) if ledger_item else {}
    open_questions = [
        str(closure_requirement.get("required_information") or "").strip(),
        str(closure_requirement.get("minimal_user_action") or "").strip(),
    ]
    open_questions = [question for question in open_questions if question]
    knowns = {
        "decision_key": decision_key,
        "state": str(ledger_item.get("state") or "unknown").strip().lower() or "unknown",
        "blocking": bool(ledger_item.get("blocking")),
        "mapping_blocking": bool(closure_requirement.get("mapping_blocking")),
        "scope_status": str(closure_requirement.get("scope_status") or "unknown").strip().lower() or "unknown",
        "selected_value": str(ledger_item.get("selected_value") or "").strip() or None,
        "alternatives": [
            str(value).strip()
            for value in list(ledger_item.get("alternatives") or [])
            if str(value).strip()
        ][:6],
        "evidence_refs": [
            str(value).strip()
            for value in list(ledger_item.get("evidence_refs") or [])
            if str(value).strip()
        ][:6],
    }
    if residual:
        knowns["residual"] = residual
    gwb = generic_knowns_snapshot(board_item) if isinstance(board_item, dict) else None
    if gwb:
        knowns["generic_work_board"] = gwb
    next_action = next_recommended_action_text([residual] if residual else [])
    return {
        "role": "sticky_note",
        "purpose": "current_case_understanding",
        "source_completeness": source_completeness,
        "knowns": knowns,
        "open_questions": open_questions,
        "recent_attempts": recent_attempts[-MAX_RECENT_ATTEMPTS:],
        "memory_summary": memory_summary[:MAX_MEMORY_SUMMARY_CHARS],
        "next_recommended_action": next_action[:MAX_MEMORY_SUMMARY_CHARS],
        "editable": True,
        "canonical": False,
    }


def _working_plan(
    *,
    decision_key: str,
    focus_source: str,
    ledger_item: dict[str, Any],
    closure_requirement: dict[str, Any],
    recent_attempts: list[dict[str, Any]],
    investigation_brief: dict[str, Any],
    active_emergent_blocker: dict[str, Any] | None,
    source_completeness: str,
    board_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    residual = baseline_residual_from_unresolved(ledger_item) if ledger_item else {}
    mapping_blocking = _canonical_mapping_blocking(ledger_item=ledger_item, closure_requirement=closure_requirement)
    focus_label = str(ledger_item.get("label") or ledger_item.get("key") or decision_key or "decision").strip()
    current_goal = (
        "increase understanding before repair"
        if mapping_blocking or str(source_completeness).strip().lower() in {"unknown", "partial"}
        else "apply the safest bounded next step"
    )
    next_action = str(investigation_brief.get("next_recommended_action") or "").strip()
    if not next_action:
        next_action = next_recommended_action_text([residual] if residual else [])
    steps: list[str] = []
    if focus_source == "emergent_blocker" and isinstance(active_emergent_blocker, dict):
        title = str(active_emergent_blocker.get("title") or focus_label).strip() or focus_label
        steps.append(f"Work the emergent blocker explicitly: {title}.")
    if mapping_blocking:
        steps.append("Verify or narrow the mapping-critical uncertainty before any speculative edit.")
    elif str(closure_requirement.get("scope_status") or "").strip().lower() == "unknown":
        steps.append("Keep scope and dependency uncertainty explicit while the case is still being oriented.")
    if next_action:
        steps.append(next_action)
    if not steps:
        steps.append("Proceed with the current bounded focus item and preserve additive state.")
    board_notes = None
    if isinstance(board_item, dict):
        bm = board_materiality(board_item)
        bs = board_state(board_item)
        if bm or bs:
            board_notes = f"generic board: materiality={bm or 'unknown'}, state={bs or 'unknown'}"
    replan_triggers = [
        "new evidence changes the ledger state or mapping impact",
        "human feedback arrives or is superseded",
        "repeated no-signal attempts suggest the current approach is stale",
        "the investigation brief gains a materially different known/open-question set",
    ]
    return {
        "role": "working_plan",
        "purpose": "short_horizon_case_rail",
        "plan_version": "working_plan_v0",
        "editable": True,
        "canonical": False,
        "status": "working" if recent_attempts or mapping_blocking else "lightweight",
        "current_focus": {
            "decision_key": decision_key,
            "label": focus_label or None,
            "focus_source": focus_source,
            "mapping_blocking": mapping_blocking,
            "scope_status": str(closure_requirement.get("scope_status") or "unknown").strip().lower() or "unknown",
        },
        "current_goal": current_goal,
        "next_steps": steps[:4],
        "replan_triggers": replan_triggers,
        "notes": str(investigation_brief.get("memory_summary") or "").strip()[:MAX_MEMORY_SUMMARY_CHARS] or None,
        "recent_attempts_seen": len(recent_attempts),
        "generic_board_snapshot": board_notes,
    }


def _derived_policy_signals(
    *,
    decision_key: str,
    ledger_item: dict[str, Any],
    closure_requirement: dict[str, Any],
    recent_attempts: list[dict[str, Any]],
    investigation_brief: dict[str, Any],
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any],
    visual_evidence: dict[str, Any],
    feedback: dict[str, Any] | None,
    source_completeness: str,
    evidence_repeat_guard: dict[str, dict[str, Any]],
    evidence_signal_counter: int,
    board_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    residual = baseline_residual_from_unresolved(ledger_item) if ledger_item else {}
    mapping_blocking = _canonical_mapping_blocking(ledger_item=ledger_item, closure_requirement=closure_requirement)
    scope_status = str(closure_requirement.get("scope_status") or "unknown").strip().lower() or "unknown"
    source_state = str(source_completeness or "unknown").strip().lower() or "unknown"
    recent_image_attempts = recent_image_evidence_attempt_count(
        continuity_log=recent_attempts,
        decision_key=decision_key,
        window=8,
    )
    image_results = []
    if isinstance(image_verification.get("results"), list):
        image_results = [row for row in image_verification.get("results") if isinstance(row, dict)]
    image_verified = any(str(row.get("status") or "").strip().lower() in {"match", "confirmed"} for row in image_results)
    visual_status = str(visual_evidence.get("status") or "").strip().lower() or None
    cached_context_present = bool(
        span_context
        or image_results
        or image_verified
        or visual_status in {"located", "verified", "captured"}
        or isinstance(feedback, dict)
    )
    repeat_signature = _policy_repeat_signature(decision_key)
    repeat_entry = evidence_repeat_guard.get(repeat_signature) if isinstance(evidence_repeat_guard, dict) else {}
    last_signal_counter = int(repeat_entry.get("last_signal_counter") or 0) if isinstance(repeat_entry, dict) else 0
    current_signal_counter = max(0, int(evidence_signal_counter or 0))
    has_fresh_signal = bool(
        current_signal_counter > last_signal_counter
        or isinstance(feedback, dict)
    )
    has_new_signal = has_fresh_signal
    if mapping_blocking and source_state in {"unknown", "partial", "partial_truncated", "partial_missing_context"}:
        understanding_strength = "weak"
    elif mapping_blocking and (has_fresh_signal or cached_context_present):
        understanding_strength = "moderate"
    elif mapping_blocking:
        understanding_strength = "moderate"
    else:
        understanding_strength = "narrow"
    needs_orientation = understanding_strength == "weak" and not bool(recent_attempts)
    needs_inventory = understanding_strength == "weak" or (mapping_blocking and not has_fresh_signal)
    repeat_without_signal = bool(recent_image_attempts >= 2 and not has_fresh_signal)
    escalation_eligible = bool(
        mapping_blocking
        and scope_status in {"in_target", "unknown"}
        and understanding_strength in {"moderate", "narrow"}
        and (has_fresh_signal or recent_image_attempts >= 1)
    )
    repair_eligible = bool(
        mapping_blocking
        and understanding_strength != "weak"
        and has_fresh_signal
    )
    focus_is_material = bool(mapping_blocking)
    board_maps = board_is_mapping_blocking(board_item) if isinstance(board_item, dict) else None
    board_mat = board_materiality(board_item) if isinstance(board_item, dict) else None
    return {
        "decision_key": decision_key,
        "understanding_strength": understanding_strength,
        "needs_orientation": needs_orientation,
        "needs_inventory": needs_inventory,
        "has_new_signal": has_new_signal,
        "has_fresh_signal": has_fresh_signal,
        "cached_context_present": cached_context_present,
        "repeat_without_signal": repeat_without_signal,
        "escalation_eligible": escalation_eligible,
        "repair_eligible": repair_eligible,
        "focus_is_material": focus_is_material,
        "generic_board_mapping_signal": board_maps,
        "generic_board_materiality": board_mat,
        "recent_image_attempts": int(recent_image_attempts),
        "source_completeness": source_state,
        "evidence_repeat_budget": int((evidence_repeat_guard.get(_policy_repeat_signature(decision_key)) or {}).get("count") or 0) if isinstance(evidence_repeat_guard, dict) else 0,
    }


def _canonical_mapping_blocking(*, ledger_item: dict[str, Any], closure_requirement: dict[str, Any]) -> bool:
    if isinstance(closure_requirement, dict) and "mapping_blocking" in closure_requirement:
        return bool(closure_requirement.get("mapping_blocking"))
    if isinstance(ledger_item, dict):
        return bool(ledger_item.get("mapping_blocking"))
    return False


def _policy_repeat_signature(decision_key: str) -> str:
    return f"{str(decision_key or '').strip().lower()}|repeat"


def _bounded_span_context(span_context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bounded: list[dict[str, Any]] = []
    for entry in span_context:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or entry.get("content") or "").strip()
        bounded.append(
            {
                "span_id": str(entry.get("span_id") or "").strip() or None,
                "text": text[:MAX_SPAN_TEXT_CHARS],
                "start_char": entry.get("start_char"),
                "end_char": entry.get("end_char"),
            }
        )
        if len(bounded) >= MAX_SPAN_COUNT:
            break
    return bounded


def _bounded_image_verification(
    *,
    image_verification_payload: dict[str, Any],
    decision_key: str,
) -> dict[str, Any]:
    payload = image_verification_payload if isinstance(image_verification_payload, dict) else {}
    out: dict[str, Any] = {
        "decision_key": decision_key,
        "summary": dict(payload.get("summary")) if isinstance(payload.get("summary"), dict) else {},
        "results": [],
    }
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    bounded_results: list[dict[str, Any]] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        bounded_results.append(
            {
                "decision_key": decision_key,
                "check_id": str(row.get("check_id") or "").strip(),
                "status": str(row.get("status") or "").strip().lower(),
                "confidence": str(row.get("confidence") or "").strip().lower(),
                "observed_text": str(row.get("observed_text") or "").strip()[:MAX_IMAGE_OBSERVED_TEXT_CHARS],
            }
        )
        if len(bounded_results) >= MAX_IMAGE_RESULTS:
            break
    out["results"] = bounded_results
    return out


def _bounded_visual_evidence(
    *,
    visual_evidence_state: dict[str, Any] | None,
    decision_key: str,
) -> dict[str, Any]:
    state = visual_evidence_state if isinstance(visual_evidence_state, dict) else {}
    locator = state.get("locator") if isinstance(state.get("locator"), dict) else {}
    verify_summary = state.get("verify_summary") if isinstance(state.get("verify_summary"), dict) else {}
    return {
        "decision_key": decision_key,
        "mode": str(state.get("mode") or "").strip().lower() or None,
        "status": str(state.get("status") or "").strip().lower() or None,
        "query": str(state.get("query") or "").strip()[:MAX_IMAGE_OBSERVED_TEXT_CHARS] or None,
        "expected_text": str(state.get("expected_text") or "").strip()[:MAX_IMAGE_OBSERVED_TEXT_CHARS] or None,
        "crop_box": dict(state.get("crop_box")) if isinstance(state.get("crop_box"), dict) else None,
        "zoom_factor": state.get("zoom_factor"),
        "inspection_ref": _bounded_ref(state.get("inspection_ref")),
        "tx_image_region_lineage_ref": _bounded_ref(state.get("tx_image_region_lineage_ref")),
        "region_lineage": dict(state.get("region_lineage")) if isinstance(state.get("region_lineage"), dict) else {},
        "image_width": state.get("image_width"),
        "image_height": state.get("image_height"),
        "grid_spec": dict(state.get("grid_spec")) if isinstance(state.get("grid_spec"), dict) else None,
        "grid_overlay_ref": _bounded_ref(state.get("grid_overlay_ref")),
        "selector_type": str(state.get("selector_type") or "").strip().lower() or None,
        "source_image_path": str(state.get("source_image_path") or "").strip() or None,
        "tx_image_evidence_region_ref": _bounded_ref(state.get("tx_image_evidence_region_ref")),
        "tx_image_evidence_context_ref": _bounded_ref(state.get("tx_image_evidence_context_ref")),
        "locator": {
            "status": str(locator.get("status") or "").strip().lower() or None,
            "confidence": str(locator.get("confidence") or "").strip().lower() or None,
            "reason": str(locator.get("reason") or "").strip()[:MAX_IMAGE_OBSERVED_TEXT_CHARS] or None,
        },
        "verify_summary": dict(verify_summary),
    }


def _bounded_ref(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        artifact_path = str(raw.get("artifact_path") or "").strip()
        if artifact_path:
            return {"artifact_path": artifact_path}
    return None


def _tri_state_in_target_scope(raw_value: Any, scope_status: str) -> bool | None:
    if isinstance(raw_value, bool):
        return raw_value
    status = str(scope_status or "").strip().lower()
    if status == "in_target":
        return True
    if status == "outside_target":
        return False
    return None


def _bounded_feedback(*, feedback: dict[str, Any] | None, decision_key: str) -> dict[str, Any] | None:
    if not isinstance(feedback, dict):
        return None
    feedback_key = str(feedback.get("decision_key") or decision_key).strip().lower()
    return {
        "decision_key": feedback_key,
        "selected_value": str(feedback.get("selected_value") or "").strip()[:MAX_FEEDBACK_VALUE_CHARS],
        "choice": str(feedback.get("choice") or "").strip()[:MAX_FEEDBACK_VALUE_CHARS] or None,
        "note": str(feedback.get("note") or "").strip()[:MAX_FEEDBACK_NOTE_CHARS] or None,
        "prompt_id": str(feedback.get("prompt_id") or "").strip()[:120] or None,
        "metadata": dict(feedback.get("metadata")) if isinstance(feedback.get("metadata"), dict) else {},
    }


def _bounded_external_context_injections(
    *,
    decision_ledger: dict[str, Any],
    decision_key: str,
) -> list[dict[str, Any]]:
    rows = decision_ledger.get("external_context_injections") if isinstance(decision_ledger, dict) else []
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    key = str(decision_key or "").strip().lower()
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("decision_key") or "").strip().lower()
        if key and row_key and row_key != key:
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        payload_summary = {
            "issue_summary": str(payload.get("issue_summary") or "").strip()[:MAX_EXTERNAL_PAYLOAD_CHARS] or None,
            "original_prompt_summary": str(payload.get("original_prompt_summary") or "").strip()[:MAX_EXTERNAL_PAYLOAD_CHARS] or None,
            "selected_choice": str(payload.get("selected_choice") or "").strip()[:MAX_EXTERNAL_PAYLOAD_CHARS] or None,
            "normalized_answer_summary": str(payload.get("normalized_answer_summary") or "").strip()[:MAX_EXTERNAL_PAYLOAD_CHARS] or None,
            "note": str(payload.get("note") or "").strip()[:MAX_EXTERNAL_PAYLOAD_CHARS] or None,
            "alternatives": [
                str(v).strip()[:MAX_EXTERNAL_PAYLOAD_CHARS]
                for v in list(payload.get("alternatives") or [])
                if str(v).strip()
            ][:6],
        }
        out.append(
            {
                "type": str(row.get("type") or "").strip().lower() or None,
                "ticket_id": str(row.get("ticket_id") or "").strip() or None,
                "decision_key": row_key or None,
                "lifecycle_state": str(row.get("lifecycle_state") or "").strip().lower() or None,
                "strength": str(row.get("strength") or "").strip().lower() or None,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "answered_at": row.get("answered_at"),
                "integrated_at": row.get("integrated_at"),
                "relevance": str(row.get("relevance") or "").strip().lower() or None,
                "payload": payload_summary,
            }
        )
        if len(out) >= MAX_EXTERNAL_CONTEXT_INJECTIONS:
            break
    return out


def _focused_blocker_pair(
    *,
    blocker_feedback_state: dict[str, Any],
    decision_key: str,
) -> dict[str, Any] | None:
    if not decision_key:
        return None
    pairs = (
        blocker_feedback_state.get("unresolved_blocker_ticket_pairs")
        if isinstance(blocker_feedback_state, dict)
        else []
    )
    if not isinstance(pairs, list):
        return None
    key = str(decision_key or "").strip().lower()
    for row in pairs:
        if not isinstance(row, dict):
            continue
        if str(row.get("decision_key") or "").strip().lower() != key:
            continue
        return dict(row)
    return None


def _focused_blocker_pair_fallback(
    *,
    decision_key: str,
    ledger_item: dict[str, Any],
    closure_requirement: dict[str, Any],
    external_injections: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not decision_key:
        return None
    state = str(ledger_item.get("state") or "unknown").strip().lower()
    mapping_blocking = bool(closure_requirement.get("mapping_blocking", ledger_item.get("blocking")))
    if not mapping_blocking or state not in {"unknown", "candidate_found", "disputed", "accepted_with_risk"}:
        return None
    latest_ticket = None
    for row in external_injections:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").strip().lower() != "human_resolution_ticket":
            continue
        if str(row.get("decision_key") or "").strip().lower() != decision_key:
            continue
        latest_ticket = row
        break
    lifecycle_state = str((latest_ticket or {}).get("lifecycle_state") or "").strip().lower() or None
    pair_state = "feedback_ready_for_integration" if lifecycle_state == "answered_unintegrated" else lifecycle_state or "no_ticket"
    return {
        "decision_key": decision_key,
        "decision_label": str(ledger_item.get("label") or decision_key),
        "blocker_state": "open",
        "associated_ticket_id": str((latest_ticket or {}).get("ticket_id") or "").strip() or None,
        "associated_ticket_state": lifecycle_state,
        "associated_ticket_relevance": str((latest_ticket or {}).get("relevance") or "").strip().lower() or None,
        "pair_state": pair_state,
        "ready_for_resolution": lifecycle_state in {"answered_unintegrated", "integration_attempted_failed"},
    }


# ---------------------------------------------------------------------------
# D1 — T0 consensus lane
# ---------------------------------------------------------------------------

def _extract_key_value_from_text(decision_key: str, text: str) -> str | None:
    """Bounded regex extraction for a single decision_key from transcript text.

    Patterns cover common PLSS/deed keys; discovery may introduce other keys with no regex here.
    """
    if decision_key == "tie_distance":
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:feet|foot|ft)\b", text, re.IGNORECASE)
        return m.group(0) if m else None
    if decision_key == "acreage":
        m = re.search(r"(\d+(?:\.\d+)?)\s*ac(?:re|res)?\b", text, re.IGNORECASE)
        return m.group(0) if m else None
    if decision_key == "tie_bearing":
        m = re.search(r"\b[NS]\s*\d{1,3}(?:\s*[°º])?(?:\s*\d{1,2})?\s*[EW]\b", text, re.IGNORECASE)
        return m.group(0) if m else None
    if decision_key in {"range", "township", "section"}:
        m = re.search(rf"{decision_key}\s*[:\-]?\s*([A-Za-z0-9 \-]+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:40]
    if decision_key == "closure_or_pob":
        lower = text.lower()
        if "point of beginning" in lower:
            return "point of beginning"
        if "pob" in lower:
            return "pob"
        if "closure" in lower:
            return "closure"
    return None


def _read_draft_text(path_str: str) -> str:
    """Read concatenated section bodies from a T0 draft JSON file. Returns "" on any failure."""
    try:
        raw = Path(path_str).read_text(encoding="utf-8")
        data = json.loads(raw)
        sections = data.get("sections") or []
        return " ".join(str(s.get("body") or "") for s in sections if isinstance(s, dict))
    except Exception:
        return ""


def _build_t0_consensus(
    *,
    decision_key: str,
    ledger_item: dict[str, Any] | None,
    closure_requirement: dict[str, Any],
    t0_candidate_refs: list[str],
) -> dict[str, Any] | None:
    """Build bounded T0 consensus lane when item is disputed + mapping-blocking and refs are available."""
    if not t0_candidate_refs:
        return None
    state = str((ledger_item or {}).get("state") or "").strip().lower()
    mapping_blocking = bool(closure_requirement.get("mapping_blocking"))
    if state != "disputed" or not mapping_blocking:
        return None

    draft_votes: list[dict[str, Any]] = []
    value_counts: dict[str, int] = {}
    for ref in t0_candidate_refs[:5]:
        text = _read_draft_text(ref)
        if not text:
            continue
        extracted = _extract_key_value_from_text(decision_key, text)
        if extracted:
            val = extracted.strip().lower()
            value_counts[val] = value_counts.get(val, 0) + 1
        draft_votes.append({"ref": ref, "extracted": extracted})

    total = len(draft_votes)
    if total == 0:
        return None

    dominant = max(value_counts, key=lambda v: value_counts[v]) if value_counts else None
    dominant_count = value_counts.get(dominant, 0) if dominant else 0
    if dominant_count == total:
        confidence = "unanimous"
    elif dominant_count > total / 2:
        confidence = "majority"
    else:
        confidence = "split"

    return {
        "draft_count": total,
        "drafts": draft_votes,
        "dominant_candidate": dominant,
        "dominant_vote_count": dominant_count,
        "value_counts": dict(value_counts),
        "confidence": confidence,
    }
