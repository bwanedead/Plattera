from __future__ import annotations

import json
from typing import Any

from .prompt_sources import (
    TRANSCRIPT_EDIT_FOCUS_AUTHORED_ATTENTION_DOCTRINE,
    TRANSCRIPT_EDIT_PLANNER_SUPPORT_STATE_DOCTRINE,
    TRANSCRIPT_EDIT_RESOLVER_SUPPORT_STATE_DOCTRINE,
)
from .work_board_emergence_hints import TRANSCRIPT_EDIT_EMERGENT_ITEM_HINTS, WORK_BOARD_EMERGENCE_DOCTRINE

_MAX_PLANNER_TEXT_CHARS = 160


def _coerce_dict(raw: Any) -> dict[str, Any] | None:
    return dict(raw) if isinstance(raw, dict) else None


def _packet_support_state(focus_packet: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(focus_packet, dict):
        return {}
    support_state = focus_packet.get("support_state")
    if isinstance(support_state, dict):
        return dict(support_state)
    out: dict[str, Any] = {}
    for key in ("investigation_brief", "item_context", "continuity_context", "evidence_context", "item_history", "unresolved_questions", "blocker_posture"):
        value = focus_packet.get(key)
        if key in {"item_history", "unresolved_questions"} and isinstance(value, list):
            out[key] = list(value)
        elif isinstance(value, dict):
            out[key] = dict(value)
    return out


def _support_state_payload(
    *,
    item_context: dict[str, Any] | None,
    continuity_context: dict[str, Any] | None,
    evidence_context: dict[str, Any] | None,
    item_history: list[dict[str, Any]] | None,
    unresolved_questions: list[str] | None,
    blocker_posture: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "investigation_brief": item_context,
        "item_context": item_context,
        "continuity_context": continuity_context,
        "evidence_context": evidence_context,
        "item_history": item_history,
        "unresolved_questions": unresolved_questions,
        "blocker_posture": blocker_posture,
    }


def _slim_text(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None


def slim_execution_context_for_planner(execution_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(execution_context, dict):
        return None
    ss = execution_context.get("support_state") if isinstance(execution_context.get("support_state"), dict) else {}
    item_context = _coerce_dict(ss.get("item_context") or ss.get("investigation_brief"))
    continuity_context = _coerce_dict(ss.get("continuity_context"))
    evidence_context = _coerce_dict(ss.get("evidence_context"))
    blocker_posture = _coerce_dict(ss.get("blocker_posture"))
    if item_context:
        item_context = {
            "role": _slim_text(item_context.get("role"), 40),
            "purpose": _slim_text(item_context.get("purpose"), 80),
            "source_completeness": _slim_text(item_context.get("source_completeness"), 24),
            "knowns": item_context.get("knowns") if isinstance(item_context.get("knowns"), dict) else {},
            "open_questions": [
                _slim_text(question, _MAX_PLANNER_TEXT_CHARS)
                for question in list(item_context.get("open_questions") or [])
                if _slim_text(question, _MAX_PLANNER_TEXT_CHARS)
            ][:4],
            "recent_attempts": [dict(row) for row in list(item_context.get("recent_attempts") or []) if isinstance(row, dict)][:4],
            "memory_summary": _slim_text(item_context.get("memory_summary"), 220),
        }
    if continuity_context:
        continuity_context = {
            "active_item_id": _slim_text(continuity_context.get("active_item_id"), 120),
            "last_focus_key": _slim_text(continuity_context.get("last_focus_key"), 120),
            "focus_source": _slim_text(continuity_context.get("focus_source"), 40),
            "focus_target_kind": _slim_text(continuity_context.get("focus_target_kind"), 40),
            "recent_attempt_count": int(continuity_context.get("recent_attempt_count") or 0),
            "active_emergent_blocker_id": _slim_text(continuity_context.get("active_emergent_blocker_id"), 120),
            "reopen_suggested": bool(continuity_context.get("reopen_suggested")),
        }
    if evidence_context:
        evidence_context = {
            "span_context": [dict(row) for row in list(evidence_context.get("span_context") or []) if isinstance(row, dict)][:4],
            "image_verification": evidence_context.get("image_verification") if isinstance(evidence_context.get("image_verification"), dict) else {},
            "visual_evidence": evidence_context.get("visual_evidence") if isinstance(evidence_context.get("visual_evidence"), dict) else {},
            "feedback": evidence_context.get("feedback") if isinstance(evidence_context.get("feedback"), dict) else None,
            "source_completeness": _slim_text(evidence_context.get("source_completeness"), 24),
            "evidence_repeat_budget": int(evidence_context.get("evidence_repeat_budget") or 0),
            "evidence_signal_counter": int(evidence_context.get("evidence_signal_counter") or 0),
            "recent_image_attempts": int(evidence_context.get("recent_image_attempts") or 0),
        }
    if blocker_posture:
        blocker_posture = {
            "understanding_strength": _slim_text(blocker_posture.get("understanding_strength"), 24),
            "needs_orientation": bool(blocker_posture.get("needs_orientation")),
            "needs_inventory": bool(blocker_posture.get("needs_inventory")),
            "has_new_signal": bool(blocker_posture.get("has_new_signal")),
            "has_fresh_signal": bool(blocker_posture.get("has_fresh_signal")),
            "cached_context_present": bool(blocker_posture.get("cached_context_present")),
            "repeat_without_signal": bool(blocker_posture.get("repeat_without_signal")),
            "recent_image_attempts": int(blocker_posture.get("recent_image_attempts") or 0),
            "source_completeness": _slim_text(blocker_posture.get("source_completeness"), 24),
        }
    return {
        "schema_version": execution_context.get("schema_version"),
        "parity": execution_context.get("parity"),
        "focus_selection": execution_context.get("focus_selection"),
        "active_work_item": execution_context.get("active_work_item"),
        "recent_iterations": execution_context.get("recent_iterations"),
        "blocker_posture": blocker_posture,
        "support_state": _support_state_payload(
            item_context=item_context,
            continuity_context=continuity_context,
            evidence_context=evidence_context,
            item_history=(item_context.get("recent_attempts") if isinstance(item_context, dict) else None),
            unresolved_questions=(item_context.get("open_questions") if isinstance(item_context, dict) else None),
            blocker_posture=blocker_posture,
        ),
    }


def build_planner_system_message() -> str:
    return (
        "You are a legal transcript edit planner. "
        "Your mission is to drive the transcript toward zero mapping-critical inaccuracies for downstream deed-to-IR and mapping loops. "
        "Propose a bounded EditPlanV0 JSON object only. "
        f"{TRANSCRIPT_EDIT_PLANNER_SUPPORT_STATE_DOCTRINE}"
        f"{TRANSCRIPT_EDIT_FOCUS_AUTHORED_ATTENTION_DOCTRINE}"
        "Startup and initial work items come from LLM orientation (support_state.item_context / support_state.continuity_context when present), not from deterministic audit taxonomies. "
        "Use execution_context.active_work_item as the focused ledger row and execution_context.recent_iterations as a bounded recent-path lane. "
        "Return EditPlanV0 JSON only; durable emergent rows are owned by the focus resolver."
    )


def build_planner_user_message(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    findings_summary: dict[str, Any],
    investigation_brief: dict[str, Any] | None = None,
    working_plan: dict[str, Any] | None = None,
    policy_signals: dict[str, Any] | None = None,
    item_context: dict[str, Any] | None = None,
    continuity_context: dict[str, Any] | None = None,
    evidence_context: dict[str, Any] | None = None,
    item_history: list[dict[str, Any]] | None = None,
    unresolved_questions: list[str] | None = None,
    top_findings: list[dict[str, Any]],
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any],
    candidate_disagreement_hints: dict[str, Any],
    mapping_priority_focus: dict[str, Any],
    execution_context: dict[str, Any] | None = None,
) -> str:
    item_context = _coerce_dict(item_context) or _coerce_dict(investigation_brief) or _coerce_dict(working_plan)
    continuity_context = _coerce_dict(continuity_context)
    evidence_context = _coerce_dict(evidence_context)
    if item_history is None and isinstance(item_context, dict):
        item_history = [dict(row) for row in list(item_context.get("recent_attempts") or []) if isinstance(row, dict)]
    if unresolved_questions is None and isinstance(item_context, dict):
        unresolved_questions = [
            str(question).strip()
            for question in list(item_context.get("open_questions") or [])
            if str(question).strip()
        ]
    schema_snippet = {
        "plan_version": "edit_plan_v0",
        "source_transcript_ref": source_transcript_ref,
        "source_transcript_hash": source_transcript_hash,
        "plan_id": "tx-plan-<id>",
        "summary": "short summary",
        "ops": [
            {
                "op_id": "op-1",
                "op_type": "replace_clause",
                "change_class": "normalization",
                "confidence": "high",
                "review_required": False,
                "reason": "short reason",
                "evidence_refs": [source_transcript_ref],
                "target": {"locator_type": "anchors", "start_anchor": "Beginning at", "end_anchor": "point of beginning", "occurrence": 1},
                "expected_old": {"old_excerpt": "NW", "old_hash": None},
                "new_text": "Northwest",
            }
        ],
        "global_flags": {"review_required": False, "rationale": "optional"},
    }
    payload = {
        "task": "Generate EditPlanV0 JSON only.",
        "constraints": ["JSON object only; no markdown.", "Every op must include expected_old.old_excerpt copied from transcript.", "Anchors preferred; offsets fallback.", "Keep edits minimal and faithful to deed semantics."],
        "schema_snippet": schema_snippet,
        "findings_summary": findings_summary,
        "investigation_brief": item_context,
        "support_state": _support_state_payload(
            item_context=item_context,
            continuity_context=continuity_context,
            evidence_context=evidence_context,
            item_history=item_history,
            unresolved_questions=unresolved_questions,
            blocker_posture=_coerce_dict((execution_context or {}).get("blocker_posture")),
        ),
        "top_findings": top_findings,
        "span_context": span_context,
        "image_verification": image_verification,
        "candidate_disagreement_hints": candidate_disagreement_hints,
        "mapping_priority_focus": mapping_priority_focus,
        "execution_context": slim_execution_context_for_planner(execution_context if isinstance(execution_context, dict) else None),
        "source_transcript_ref": source_transcript_ref,
        "source_transcript_hash": source_transcript_hash,
        "item_history": item_history,
        "unresolved_questions": unresolved_questions,
    }
    return json.dumps(payload, ensure_ascii=False)


def build_plan_repair_user_message(*, error_reason: str, raw_content: str, source_transcript_ref: str, source_transcript_hash: str) -> str:
    return json.dumps(
        {
            "task": "Repair your previous plan. Return valid EditPlanV0 JSON only.",
            "error_reason": error_reason,
            "previous_output_excerpt": (raw_content or "")[:1200],
            "minimal_valid_example": {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": source_transcript_ref,
                "source_transcript_hash": source_transcript_hash,
                "plan_id": "tx-plan-repair-1",
                "summary": "example",
                "ops": [],
                "global_flags": {"review_required": False},
            },
            "required_fields": ["plan_version", "source_transcript_ref", "source_transcript_hash", "plan_id", "summary", "ops", "global_flags"],
            "note_on_item_context": "Treat the item_context as the sticky-note summary of the case and keep it bounded.",
            "note_on_continuity_context": "Treat continuity_context as the active-item rail, not as a planner.",
            "note_on_evidence_context": "Treat evidence_context as bounded observations, not as doctrine.",
            "note": "If no safe edit is justified, return ops=[] with rationale.",
        },
        ensure_ascii=False,
    )


def build_focus_resolver_system_message() -> str:
    return (
        "You are a transcript-edit focus resolver. "
        "Return one bounded JSON move object for the current focus item. "
        "support_state.audit_evidence_snapshot is mechanical inspection output (counts, observations) — not authoritative issue truth; "
        "you interpret evidence and author meaning via support_state.item_context / support_state.investigation_brief, support_state.continuity_context, support_state.evidence_context, "
        "support_state.item_history, support_state.unresolved_questions, and explicit move payloads (iteration_understanding, work_board_changes, blocker_updates). "
        f"{TRANSCRIPT_EDIT_FOCUS_AUTHORED_ATTENTION_DOCTRINE}"
        "The runtime carries continuity when it exists; if continuity is absent, the startup understanding authors the initial focus and candidate context remains advisory. "
        "It is valid to create emergent focus items or blockers when the case needs separate investigation, orientation, or baseline-building work; "
        "use propose_blocker_updates with custom:<name> blocker_kind when that is the best way to make the work explicit. "
        f"{TRANSCRIPT_EDIT_RESOLVER_SUPPORT_STATE_DOCTRINE}"
        "Organized work is one harness decision ledger; focus_packet.work_board is that ledger envelope (historical JSON field name). "
        "Allowed move values: apply_edit_plan, request_human_feedback, gather_more_evidence, mark_blocked, mark_resolved_no_edit, propose_blocker_updates, propose_work_board_changes. "
        "If move=apply_edit_plan, include a valid EditPlanV0 in edit_plan. "
        "If move=propose_blocker_updates, include blocker_updates[] with structured operations only (add/update/resolve/supersede). "
        "If move=propose_work_board_changes, include work_board_changes[] (decision-ledger mutations; see work_board_emergence in user payload). "
        f"{WORK_BOARD_EMERGENCE_DOCTRINE} "
        "For EditPlanV0 ops, each op must include discriminator field op_type with one of: replace_span, replace_line, replace_clause, rewrite_section. "
        "If move=request_human_feedback, include feedback_prompt with line1, line2, and bounded choices when available. "
        "If move=gather_more_evidence, include evidence_request with fields: kind, decision_key, reason, target. "
        "Allowed evidence_request.kind values: open_spans, image_verify, image_evidence, retrieve_dependency_evidence. "
        "For image_evidence use crop_box_normalized and zoom_factor; crop_box_normalized is a dict with \"x\", \"y\", \"width\", and \"height\". "
        "Treat external_context_injections as persistent semantic state. "
        "Treat blocker_registry and blocker_feedback_state as authoritative loop-state context for blocker counts, HITL pairing, and feedback integration readiness. "
        "A binding human_resolution_ticket that is answered_unintegrated must not be ignored. "
        "If focus_source=emergent_blocker, use active_emergent_blocker as the primary reasoning frame for this iteration. "
        "Legacy decision_key fields remain compatibility scaffolding and should be treated as secondary when blocker-centered focus is active. "
        "custom:<name> blocker_kind is allowed when needed. "
        "Investigation, orientation, and baseline-building may themselves become explicit blocker or focus items when that is the clearest way to preserve progress and state. "
        "Prioritize removing open mapping blockers before optional work; when focused_blocker_feedback_pair.ready_for_resolution=true, your next move must directly integrate or safely escalate that blocker-ticket pair. "
        "Do not ignore provided human feedback. "
        "If no visual evidence is yet present for an image-visible dispute and you are about to request HITL, prefer one image_evidence step first so the HITL prompt can carry the region the agent examined; then request HITL the following iteration. Do not chain more than one image_evidence step before HITL. "
        "If HITL feedback is present for the focused decision_key, you must explicitly use that feedback when selecting the move."
    )


def build_focus_resolver_user_message(*, focus_packet: dict[str, Any]) -> str:
    injections = [row for row in list(focus_packet.get("external_context_injections") or []) if isinstance(row, dict)] if isinstance(focus_packet, dict) else []
    feedback = focus_packet.get("feedback") if isinstance(focus_packet, dict) and isinstance(focus_packet.get("feedback"), dict) else None
    support_state = _packet_support_state(focus_packet if isinstance(focus_packet, dict) else None)
    item_context = _coerce_dict(support_state.get("item_context") or support_state.get("investigation_brief"))
    continuity_context = _coerce_dict(support_state.get("continuity_context"))
    evidence_context = _coerce_dict(support_state.get("evidence_context"))
    item_history = list(support_state.get("item_history") or [])
    unresolved_questions = list(support_state.get("unresolved_questions") or [])
    blocker_posture = _coerce_dict(support_state.get("blocker_posture"))
    has_feedback = isinstance(feedback, dict)
    payload = {
        "task": "Choose one next move for this focus-cycle item.",
        "execution_context": focus_packet.get("execution_context") if isinstance(focus_packet, dict) and isinstance(focus_packet.get("execution_context"), dict) else None,
        "allowed_moves": ["apply_edit_plan", "request_human_feedback", "gather_more_evidence", "mark_blocked", "mark_resolved_no_edit", "propose_blocker_updates", "propose_work_board_changes"],
        "work_board_emergence": {
            "doctrine": WORK_BOARD_EMERGENCE_DOCTRINE,
            "add_item_fields": ["op:add_item", "title", "kind", "reason", "materiality", "blocking_impact", "resolution_condition", "dependencies", "evidence_refs", "scope", "domain_payload", "context_note", "state", "priority"],
            "attach_note_fields": ["op:attach_note", "target_item_id", "note", "note_intent"],
            "update_item_state_fields": ["op:update_item_state", "target_item_id", "new_state", "reason"],
            "transcript_edit_hints": TRANSCRIPT_EDIT_EMERGENT_ITEM_HINTS,
        },
        "required_fields": ["decision_key", "move", "reason", "iteration_summary"],
        "focus_packet": focus_packet,
        "support_state": _support_state_payload(item_context=item_context, continuity_context=continuity_context, evidence_context=evidence_context, item_history=item_history, unresolved_questions=unresolved_questions, blocker_posture=blocker_posture),
        "investigation_brief": item_context,
        "item_context": item_context,
        "continuity_context": continuity_context,
        "evidence_context": evidence_context,
        "item_history": item_history,
        "unresolved_questions": unresolved_questions,
        "external_context_injections": injections,
        "blocker_feedback_state": dict(focus_packet.get("blocker_feedback_state")) if isinstance(focus_packet, dict) and isinstance(focus_packet.get("blocker_feedback_state"), dict) else {},
        "focused_blocker_feedback_pair": dict(focus_packet.get("focused_blocker_feedback_pair")) if isinstance(focus_packet, dict) and isinstance(focus_packet.get("focused_blocker_feedback_pair"), dict) else None,
        "hitl_alert": (
            {"severity": "high", "code": "HITL_FEEDBACK_PRESENT", "message": "ALERT: HITL feedback received. You must incorporate this feedback to resolve the focused blocker.", "decision_key": str((feedback or {}).get("decision_key") or focus_packet.get("decision_key") or "").strip().lower(), "selected_value": str((feedback or {}).get("selected_value") or "").strip() or None, "prompt_id": str((feedback or {}).get("prompt_id") or "").strip() or None, "note": str((feedback or {}).get("note") or "").strip() or None}
            if has_feedback
            else {"severity": "info", "code": "NO_HITL_FEEDBACK_PRESENT", "message": "No HITL feedback currently attached to the focused item."}
        ),
        "blocker_resolution_protocol": [
            "Resolve mapping blockers before non-blocking cleanup.",
            "Use focused_blocker_feedback_pair + ticket state to decide whether to integrate feedback now, wait for feedback, or issue refined ticket.",
            "If blocker reason changed and prior ticket is stale/superseded, request new focused feedback and explain why prior ticket is being replaced.",
            "Archetype menu rows are suggestions only; custom:<name> blocker_kind is valid for situational blockers.",
        ],
        "required_feedback_handling": [
            "Use provided HITL feedback as authoritative operator signal for the focused decision unless directly contradicted by stronger explicit source evidence.",
            "State in reason/iteration_summary how the move uses the feedback.",
            "If feedback cannot be safely integrated, return mark_blocked with explicit integration-failure reason.",
        ] if has_feedback else [],
        "output_shape": {
            "decision_key": "range",
            "move": "apply_edit_plan",
            "reason": "short reason",
            "edit_plan": {
                "plan_version": "edit_plan_v0",
                "plan_id": "tx-plan-range-1",
                "summary": "Normalize Range to confirmed value",
                "ops": [
                    {"op_id": "op-range-1", "op_type": "replace_clause", "change_class": "semantic", "confidence": "high", "review_required": True, "reason": "Human confirmed Range 75 West; replace incorrect Range 74 token", "evidence_refs": [], "target": {"locator_type": "anchors", "start_anchor": "Range Seventy-four", "end_anchor": "West", "occurrence": 1}, "expected_old": {"old_excerpt": "Range Seventy-four (74) West", "old_hash": None}, "new_text": "Range Seventy-five (75) West"}
                ],
                "global_flags": {"review_required": True},
            },
            "blocker_updates": [
                {"operation": "add", "blocker_kind": "source_truncation", "title": "Page Edge Truncates Call", "blocking_class": "source_blocking", "reason": "Scan cutoff removes downstream boundary call text.", "evidence_summary": "Right margin cutoff visible at end of legal description.", "resolution_condition": "Need additional page or clearer scan.", "scope_status": "unknown"},
                {"operation": "add", "blocker_kind": "custom:scan_overwrite_ambiguity", "title": "Overwrite On Bearing Token", "blocking_class": "mapping_blocking", "reason": "Overwritten symbol changes bearing interpretation.", "scope_status": "in_target"},
            ],
            "feedback_prompt": None,
            "evidence_request": {"kind": "image_evidence", "decision_key": "range", "reason": "Inspect the range clause region in the source image to resolve the R74/R75 ambiguity.", "target": {"crop_box_normalized": {"x": 0.35, "y": 0.20, "width": 0.35, "height": 0.15}, "zoom_factor": 2.4, "expected_fields": ["range"]}},
            "closure_update_hint": None,
            "work_board_changes": [
                {"op": "add_item", "title": "Explicit preserve: scan margin may truncate boundary call", "kind": "transcript_edit.investigation_branch", "reason": "Margin crop visible; need durable branch so closure work does not silently drop dependency check.", "materiality": "high", "blocking_impact": "mapping_blocking", "resolution_condition": "Obtain clearer scan or confirm call text before mapping.", "dependencies": [], "evidence_refs": ["image:margin_check_1"], "scope": {}, "domain_payload": {"hint": "not a new ledger key"}, "context_note": "May be artifact; do not over-index until scope confirmed."},
                {"op": "attach_note", "target_item_id": "te:ledger:range", "note": "Operator flagged possible OCR confusables on range digit; treat as advisory until image confirms.", "note_intent": "anti_overindex"},
            ],
            "iteration_summary": "short summary",
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def build_focus_resolver_repair_user_message(*, error_reason: str, raw_content: str, decision_key: str, injection_context: dict[str, Any] | None = None, attempt: int | None = None, max_attempts: int | None = None) -> str:
    return json.dumps(
        {
            "task": "Repair previous output and return one valid focus move object.",
            "error_reason": error_reason,
            "decision_key": decision_key,
            "previous_output_excerpt": (raw_content or "")[:1200],
            "required_fields": ["decision_key", "move", "reason", "iteration_summary"],
            "allowed_moves": ["apply_edit_plan", "request_human_feedback", "gather_more_evidence", "mark_blocked", "mark_resolved_no_edit", "propose_blocker_updates", "propose_work_board_changes"],
            "injection_context": injection_context,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "instruction": "Keep the repair bounded and treat item_context, continuity_context, and evidence_context as observations rather than doctrine.",
        },
        ensure_ascii=False,
    )
