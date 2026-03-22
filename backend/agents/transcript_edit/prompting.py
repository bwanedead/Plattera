from __future__ import annotations

import json
from typing import Any

from .work_board_emergence_hints import (
    TRANSCRIPT_EDIT_EMERGENT_ITEM_HINTS,
    WORK_BOARD_EMERGENCE_DOCTRINE,
)

_MAX_PLANNER_WORKING_PLAN_STEP_CHARS = 160


def slim_execution_context_for_planner(execution_context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop duplicate bulk from execution_context for edit-planner prompts (bounded)."""
    if not isinstance(execution_context, dict):
        return None
    ss = execution_context.get("support_state") if isinstance(execution_context.get("support_state"), dict) else {}
    wp = ss.get("working_plan") if isinstance(ss.get("working_plan"), dict) else {}
    slim_wp = None
    if wp:
        slim_wp = {
            "current_goal": str(wp.get("current_goal") or "").strip()[:200] or None,
            "status": str(wp.get("status") or "").strip()[:32] or None,
            "next_steps": [
                str(s).strip()[:_MAX_PLANNER_WORKING_PLAN_STEP_CHARS]
                for s in list(wp.get("next_steps") or [])
                if str(s).strip()
            ][:4],
        }
    return {
        "schema_version": execution_context.get("schema_version"),
        "parity": execution_context.get("parity"),
        "focus_selection": execution_context.get("focus_selection"),
        "active_work_item": execution_context.get("active_work_item"),
        "recent_iterations": execution_context.get("recent_iterations"),
        "blocker_posture": execution_context.get("blocker_posture"),
        "support_state": {
            "policy_signals": ss.get("policy_signals") if isinstance(ss.get("policy_signals"), dict) else {},
            "working_plan": slim_wp,
        },
    }


def build_planner_system_message() -> str:
    # Trunk covers: "Return only valid JSON. Never output prose or markdown." + "Be faithful to source material."
    # Branch covers: "Mapping-blocking unresolved items are the highest priority focus."
    return (
        "You are a legal transcript edit planner. "
        "Your mission is to drive the transcript toward zero mapping-critical inaccuracies for downstream deed-to-IR and mapping loops. "
        "Propose a bounded EditPlanV0 JSON object only. "
        "Treat support_state.investigation_brief / the investigation brief as a living sticky note for the case, not as canonical truth. "
        "Treat support_state.working_plan as a revisable short-horizon rail, not as doctrine. "
        "Treat support_state.policy_signals as derived runtime posture, not as doctrine or truth. "
        "Do not behave like a scripted checklist runner; choose the next bounded move from the evolving case model. "
        "Startup and initial work items come from LLM orientation (support_state.llm_startup_understanding when present), not from deterministic audit taxonomies. "
        "For deed-style transcript work, common concerns often include legal-description identity, contradictions, dependencies, tie data, closure, and acreage — but these are situational hints, not a required checklist. "
        "If uncertainty remains, keep the plan bounded and honest rather than forcing a speculative edit. "
        "Prioritize sanity and avoid speculative edits. "
        "Never treat unresolved bearing/range/tie-distance conflicts as done; plans must explicitly target unresolved conflicts when evidence supports a safe edit. "
        "Do not propose purely cosmetic formatting edits (spacing, punctuation, symbol variants) unless meaning changes. "
        "Prefer localized normalization edits first. "
        "If a finding indicates numeric/PLSS inconsistency and context provides a clear dominant value, "
        "you may propose a localized semantic correction with review_required=true. "
        "Each op must include drift-safe expected_old.old_excerpt from verbatim transcript text. "
        "Prefer anchors locator; use offsets only when anchors are unreliable. "
        "Do not produce cross-section edits unless strictly necessary. "
        "If findings do not justify changes, return an empty ops list with rationale. "
        "When execution_context is provided, treat execution_context.active_work_item as the generic harness view "
        "of the focused row on the unified decision ledger (parity flags reconcile transcript-edit checklist vs envelope). "
        "Use execution_context.recent_iterations as a bounded recent-path lane, not a full transcript or raw history. "
        "Return EditPlanV0 JSON only for this surface; durable emergent ledger rows (add-item batches) "
        "are owned by the focus resolver, not this planner."
    )


def build_planner_user_message(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    findings_summary: dict[str, Any],
    investigation_brief: dict[str, Any] | None = None,
    working_plan: dict[str, Any] | None = None,
    policy_signals: dict[str, Any] | None = None,
    top_findings: list[dict[str, Any]],
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any],
    candidate_disagreement_hints: dict[str, Any],
    mapping_priority_focus: dict[str, Any],
    execution_context: dict[str, Any] | None = None,
) -> str:
    if working_plan is None and isinstance(investigation_brief, dict):
        working_plan = {
            "role": "working_plan",
            "purpose": "short_horizon_case_rail",
            "editable": True,
            "canonical": False,
        }
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
                "target": {
                    "locator_type": "anchors",
                    "start_anchor": "Beginning at",
                    "end_anchor": "point of beginning",
                    "occurrence": 1,
                },
                "expected_old": {"old_excerpt": "NW", "old_hash": None},
                "new_text": "Northwest",
            }
        ],
        "global_flags": {"review_required": False, "rationale": "optional"},
    }
    payload = {
        "task": "Generate EditPlanV0 JSON only.",
        "constraints": [
            "JSON object only; no markdown.",
            "Every op must include expected_old.old_excerpt copied from transcript.",
            "Anchors preferred; offsets fallback.",
            "Keep edits minimal and faithful to deed semantics.",
        ],
        "schema_snippet": schema_snippet,
        "findings_summary": findings_summary,
        "investigation_brief": investigation_brief,
        "support_state": {
            "investigation_brief": investigation_brief,
            "working_plan": working_plan,
            "policy_signals": policy_signals,
        },
        "top_findings": top_findings,
        "span_context": span_context,
        "image_verification": image_verification,
        "candidate_disagreement_hints": candidate_disagreement_hints,
        "mapping_priority_focus": mapping_priority_focus,
        "execution_context": slim_execution_context_for_planner(
            execution_context if isinstance(execution_context, dict) else None
        ),
    }
    return json.dumps(payload, ensure_ascii=False)


def build_plan_repair_user_message(
    *,
    error_reason: str,
    raw_content: str,
    source_transcript_ref: str,
    source_transcript_hash: str,
) -> str:
    payload = {
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
        "required_fields": [
            "plan_version",
            "source_transcript_ref",
            "source_transcript_hash",
            "plan_id",
            "summary",
            "ops",
            "global_flags",
        ],
        "note_on_investigation": "If uncertainty remains, use the investigation brief as a sticky note and keep the plan bounded rather than inventing unsupported edits.",
        "note_on_working_plan": "The working plan is a revisable rail, not doctrine; keep it short-horizon and update it by selecting a better bounded move, not by inventing hidden steps.",
        "note_on_policy_signals": "Derived policy signals express weak vs narrow understanding, repetition pressure, and escalation/repair eligibility; use them as posture, not as a script.",
        "note": "If no safe edit is justified, return ops=[] with rationale.",
    }
    return json.dumps(payload, ensure_ascii=False)


def build_focus_resolver_system_message() -> str:
    return (
        "You are a transcript-edit focus resolver. "
        "Return one bounded JSON move object for the current focus item. "
        "support_state.audit_evidence_snapshot is mechanical inspection output (counts, observations) — not authoritative issue truth; "
        "you interpret evidence and author meaning via support_state.llm_startup_understanding, support_state.llm_iteration_understanding, "
        "and explicit move payloads (iteration_understanding, work_board_changes, blocker_updates). "
        "Do not behave like a scripted checklist runner; choose the next bounded move from the evolving case model. "
        "The runtime preselects the focus decision_key; do not switch focus to any other item. "
        "It is valid to create emergent focus items or blockers when the case needs separate investigation, orientation, or baseline-building work; "
        "use propose_blocker_updates with custom:<name> blocker_kind when that is the best way to make the work explicit. "
        "Treat support_state.investigation_brief as the current sticky-note summary of the run; it is editable, additive context, not canonical truth. "
        "Treat support_state.working_plan as a revisable short-horizon rail; it may be adjusted when the case understanding changes. "
        "Treat support_state.policy_signals as derived posture: weak understanding should bias toward orientation/inventory/verification, narrow understanding may permit repair or bounded HITL, and repeated no-signal work should be discouraged. "
        "Organized work is one harness decision ledger; focus_packet.work_board is that ledger envelope (historical JSON field name). "
        "Allowed move values: apply_edit_plan, request_human_feedback, gather_more_evidence, mark_blocked, mark_resolved_no_edit, propose_blocker_updates, propose_work_board_changes. "
        "If move=apply_edit_plan, include a valid EditPlanV0 in edit_plan. "
        "If move=propose_blocker_updates, include blocker_updates[] with structured operations only (add/update/resolve/supersede). "
        "If move=propose_work_board_changes, include work_board_changes[] (decision-ledger mutations; see work_board_emergence in user payload). "
        "work_board_changes may include op=update_item_state for harness:emergent:* rows only (new_state, reason) — use for supersede/resolve when a branch is absorbed. "
        f"{WORK_BOARD_EMERGENCE_DOCTRINE} "
        "For EditPlanV0 ops, each op must include discriminator field op_type with one of: replace_span, replace_line, replace_clause, rewrite_section. "
        "If move=request_human_feedback, include feedback_prompt with line1, line2, and bounded choices when available. "
        "If move=gather_more_evidence, include evidence_request with fields: kind, decision_key, reason, target. "
        "Allowed evidence_request.kind values: open_spans, image_verify, image_evidence, retrieve_dependency_evidence. "
        "For image_evidence: set target to a JSON object with crop_box_normalized ({\"x\": float, \"y\": float, \"width\": float, \"height\": float} with values in 0-1 range) and zoom_factor (1.0–4.0). "
        "For open_spans: set target to a span_key or description of the region of interest. "
        "For retrieve_dependency_evidence: set target to the dependency key or artifact ref to retrieve. "
        "Treat external_context_injections as persistent semantic state. "
        "Treat blocker_registry and blocker_feedback_state as authoritative loop-state context for blocker counts, HITL pairing, and feedback integration readiness. "
        "If focus_source=emergent_blocker, use active_emergent_blocker as the primary reasoning frame for this iteration. "
        "Legacy decision_key fields remain compatibility scaffolding and should be treated as secondary when blocker-centered focus is active. "
        "Treat blocker_registry.archetype_menu as optional scaffolding only: use archetypes when they fit, but custom:<name> blocker_kind is allowed when needed. "
        "Investigation, orientation, and baseline-building may themselves become explicit blocker or focus items when that is the clearest way to preserve progress and state. "
        "A sane focus item can be exploratory or planning-oriented if that is what the case needs next. "
        "Prioritize removing open mapping blockers before optional work; when focused_blocker_feedback_pair.ready_for_resolution=true, your next move must directly integrate or safely escalate that blocker-ticket pair. "
        "HITL_SEMANTICS (Phase 22): Distinguish locator evidence from corrected truth. "
        "If the operator points at or quotes the incorrect on-transcript token/span, that text belongs in expected_old.old_excerpt (what to replace), not in new_text. "
        "new_text must be the authoritative corrected value (from choices, selected_value when it states the correct PLSS reading, or ledger alternatives) — never treat a locator excerpt as the replacement text. "
        "If move=apply_edit_plan, each op must replace an excerpt that actually appears in the current working transcript with the intended correction direction (wrong→right), not the reverse. "
        "If HITL feedback is present for the focused decision_key, you must explicitly use that feedback when selecting the move. "
        "Do not ignore provided human feedback. "
        "If prior ticket wording no longer matches the blocker reason, close/supersede that ticket and emit a refined replacement feedback request with explicit reason change. "
        "When feedback is present, your reason and iteration_summary must state how the selected move incorporates the feedback. "
        "If a binding human_resolution_ticket is answered_unintegrated for the focused decision_key, you must choose a move that addresses integration directly "
        "(apply_edit_plan, explicit blocked reason, tighter follow-up feedback, or clearly justified different evidence). "
        "When focus_packet.validation_mode=live_hitl and the focused item has state=disputed or verification_required=true, "
        "you MUST prefer request_human_feedback over gather_more_evidence. "
        "Do NOT re-audit or gather evidence for a disputed item when live HITL is available — the human operator is the resolution authority. "
        "Exception: if no visual evidence is yet present for an image-visible dispute and you are about to request HITL, "
        "prefer one image_evidence step first (agent-selected crop/zoom) so the HITL prompt can carry the region the agent examined; "
        "then request HITL the following iteration. Do not chain more than one image_evidence step before HITL. "
        "Optional: include iteration_understanding (same general shape as startup understanding) to merge LLM-authored ledger/blocker updates after interpreting evidence. "
        "Always include decision_key, move, reason, and iteration_summary. "
        "When execution_context is present, use execution_context.recent_iterations for bounded recent-path memory "
        "(rich tail + short summaries); it is not a full run archive. "
        "Prefer execution_context.active_work_item as the generic harness view of the focused decision-ledger row."
    )


def build_focus_resolver_user_message(
    *,
    focus_packet: dict[str, Any],
) -> str:
    injections = (
        [row for row in list(focus_packet.get("external_context_injections") or []) if isinstance(row, dict)]
        if isinstance(focus_packet, dict)
        else []
    )
    feedback = focus_packet.get("feedback") if isinstance(focus_packet, dict) and isinstance(focus_packet.get("feedback"), dict) else None
    has_feedback = isinstance(feedback, dict)
    feedback_decision_key = str((feedback or {}).get("decision_key") or "").strip().lower()
    feedback_selected_value = str((feedback or {}).get("selected_value") or "").strip()
    feedback_note = str((feedback or {}).get("note") or "").strip()
    feedback_prompt_id = str((feedback or {}).get("prompt_id") or "").strip()
    blocker_feedback_state = (
        dict(focus_packet.get("blocker_feedback_state"))
        if isinstance(focus_packet, dict) and isinstance(focus_packet.get("blocker_feedback_state"), dict)
        else {}
    )
    focused_blocker_pair = (
        dict(focus_packet.get("focused_blocker_feedback_pair"))
        if isinstance(focus_packet, dict) and isinstance(focus_packet.get("focused_blocker_feedback_pair"), dict)
        else {}
    )
    working_plan = (
        dict(focus_packet.get("working_plan"))
        if isinstance(focus_packet, dict) and isinstance(focus_packet.get("working_plan"), dict)
        else (
            {
                "role": "working_plan",
                "purpose": "short_horizon_case_rail",
                "editable": True,
                "canonical": False,
            }
            if isinstance(focus_packet, dict) and isinstance(focus_packet.get("investigation_brief"), dict)
            else None
        )
    )
    support_state = (
        dict(focus_packet.get("support_state"))
        if isinstance(focus_packet, dict) and isinstance(focus_packet.get("support_state"), dict)
        else (
            {
                "investigation_brief": focus_packet.get("investigation_brief") if isinstance(focus_packet, dict) else None,
                "working_plan": working_plan,
            }
            if isinstance(focus_packet, dict)
            else None
        )
    )
    execution_context = (
        focus_packet.get("execution_context") if isinstance(focus_packet, dict) else None
    )
    payload = {
        "task": "Choose one next move for this focus-cycle item.",
        "execution_context": execution_context if isinstance(execution_context, dict) else None,
        "allowed_moves": [
            "apply_edit_plan",
            "request_human_feedback",
            "gather_more_evidence",
            "mark_blocked",
            "mark_resolved_no_edit",
            "propose_blocker_updates",
            "propose_work_board_changes",
        ],
        "work_board_emergence": {
            "doctrine": WORK_BOARD_EMERGENCE_DOCTRINE,
            "add_item_fields": [
                "op:add_item",
                "title",
                "kind",
                "reason",
                "materiality",
                "blocking_impact",
                "resolution_condition",
                "dependencies",
                "evidence_refs",
                "scope",
                "domain_payload",
                "context_note",
                "state",
                "priority",
            ],
            "attach_note_fields": ["op:attach_note", "target_item_id", "note", "note_intent"],
            "update_item_state_fields": ["op:update_item_state", "target_item_id", "new_state", "reason"],
            "transcript_edit_hints": TRANSCRIPT_EDIT_EMERGENT_ITEM_HINTS,
        },
        "required_fields": ["decision_key", "move", "reason", "iteration_summary"],
        "focus_packet": focus_packet,
        "support_state": support_state,
        "investigation_brief": focus_packet.get("investigation_brief") if isinstance(focus_packet, dict) else None,
        "working_plan": working_plan,
        "policy_signals": (
            support_state.get("policy_signals")
            if isinstance(support_state, dict) and support_state.get("policy_signals") is not None
            else (focus_packet.get("policy_signals") if isinstance(focus_packet, dict) else None)
        ),
        "external_context_injections": injections,
        "blocker_feedback_state": blocker_feedback_state,
        "focused_blocker_feedback_pair": focused_blocker_pair or None,
        "hitl_alert": (
            {
                "severity": "high",
                "code": "HITL_FEEDBACK_PRESENT",
                "message": (
                    "ALERT: HITL feedback received. You must incorporate this feedback to resolve the focused blocker."
                ),
                "decision_key": feedback_decision_key or str(focus_packet.get("decision_key") or "").strip().lower(),
                "selected_value": feedback_selected_value or None,
                "prompt_id": feedback_prompt_id or None,
                "note": feedback_note or None,
            }
            if has_feedback
            else {
                "severity": "info",
                "code": "NO_HITL_FEEDBACK_PRESENT",
                "message": "No HITL feedback currently attached to the focused item.",
            }
        ),
        "blocker_resolution_protocol": [
            "Resolve mapping blockers before non-blocking cleanup.",
            "Use focused_blocker_feedback_pair + ticket state to decide whether to integrate feedback now, wait for feedback, or issue refined ticket.",
            "If blocker reason changed and prior ticket is stale/superseded, request new focused feedback and explain why prior ticket is being replaced.",
            "Archetype menu rows are suggestions only; custom:<name> blocker_kind is valid for situational blockers.",
        ],
        "required_feedback_handling": (
            [
                "Use provided HITL feedback as authoritative operator signal for the focused decision unless directly contradicted by stronger explicit source evidence.",
                "State in reason/iteration_summary how the move uses the feedback.",
                "If feedback cannot be safely integrated, return mark_blocked with explicit integration-failure reason.",
            ]
            if has_feedback
            else []
        ),
        "output_shape": {
            "decision_key": "range",
            "move": "apply_edit_plan",
            "reason": "short reason",
            "edit_plan": {
                "plan_version": "edit_plan_v0",
                "plan_id": "tx-plan-range-1",
                "summary": "Normalize Range to confirmed value",
                "ops": [
                    {
                        "op_id": "op-range-1",
                        "op_type": "replace_clause",
                        "change_class": "semantic",
                        "confidence": "high",
                        "review_required": True,
                        "reason": "Human confirmed Range 75 West; replace incorrect Range 74 token",
                        "evidence_refs": [],
                        "target": {
                            "locator_type": "anchors",
                            "start_anchor": "Range Seventy-four",
                            "end_anchor": "West",
                            "occurrence": 1,
                        },
                        "expected_old": {"old_excerpt": "Range Seventy-four (74) West", "old_hash": None},
                        "new_text": "Range Seventy-five (75) West",
                    }
                ],
                "global_flags": {"review_required": True},
            },
            "blocker_updates": [
                {
                    "operation": "add",
                    "blocker_kind": "source_truncation",
                    "title": "Page Edge Truncates Call",
                    "blocking_class": "source_blocking",
                    "reason": "Scan cutoff removes downstream boundary call text.",
                    "evidence_summary": "Right margin cutoff visible at end of legal description.",
                    "resolution_condition": "Need additional page or clearer scan.",
                    "scope_status": "unknown",
                },
                {
                    "operation": "add",
                    "blocker_kind": "custom:scan_overwrite_ambiguity",
                    "title": "Overwrite On Bearing Token",
                    "blocking_class": "mapping_blocking",
                    "reason": "Overwritten symbol changes bearing interpretation.",
                    "scope_status": "in_target",
                },
            ],
            "feedback_prompt": None,
            "evidence_request": {
                "kind": "image_evidence",
                "decision_key": "range",
                "reason": "Inspect the range clause region in the source image to resolve the R74/R75 ambiguity.",
                "target": {
                    "crop_box_normalized": {"x": 0.35, "y": 0.20, "width": 0.35, "height": 0.15},
                    "zoom_factor": 2.4,
                    "expected_fields": ["range"],
                },
            },
            "closure_update_hint": None,
            "work_board_changes": [
                {
                    "op": "add_item",
                    "title": "Explicit preserve: scan margin may truncate boundary call",
                    "kind": "transcript_edit.investigation_branch",
                    "reason": "Margin crop visible; need durable branch so closure work does not silently drop dependency check.",
                    "materiality": "high",
                    "blocking_impact": "mapping_blocking",
                    "resolution_condition": "Obtain clearer scan or confirm call text before mapping.",
                    "dependencies": [],
                    "evidence_refs": ["image:margin_check_1"],
                    "scope": {},
                    "domain_payload": {"hint": "not a new ledger key"},
                    "context_note": "May be artifact; do not over-index until scope confirmed.",
                },
                {
                    "op": "attach_note",
                    "target_item_id": "te:ledger:range",
                    "note": "Operator flagged possible OCR confusables on range digit; treat as advisory until image confirms.",
                    "note_intent": "anti_overindex",
                },
            ],
            "iteration_summary": "short summary",
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def build_focus_resolver_repair_user_message(
    *,
    error_reason: str,
    raw_content: str,
    decision_key: str,
    injection_context: dict[str, Any] | None = None,
    attempt: int | None = None,
    max_attempts: int | None = None,
) -> str:
    payload = {
        "task": "Repair previous output and return one valid focus move object.",
        "error_reason": error_reason,
        "decision_key": decision_key,
        "previous_output_excerpt": (raw_content or "")[:1200],
        "required_fields": ["decision_key", "move", "reason", "iteration_summary"],
        "allowed_moves": [
            "apply_edit_plan",
            "request_human_feedback",
            "gather_more_evidence",
            "mark_blocked",
            "mark_resolved_no_edit",
            "propose_blocker_updates",
            "propose_work_board_changes",
        ],
        "move_contract": {
            "apply_edit_plan_requires": ["edit_plan"],
            "request_human_feedback_requires": ["feedback_prompt"],
            "gather_more_evidence_requires": ["evidence_request"],
            "mark_blocked_requires": ["reason"],
            "mark_resolved_no_edit_requires": ["reason"],
            "propose_work_board_changes_requires": ["work_board_changes"],
        },
        "edit_plan_requirements": {
            "ops_item_requires": ["op_id", "op_type", "change_class", "confidence", "review_required", "reason", "target", "expected_old", "new_text"],
            "allowed_op_type": ["replace_span", "replace_line", "replace_clause", "rewrite_section"],
            "allowed_change_class": ["normalization", "semantic"],
            "allowed_confidence": ["high", "medium", "low"],
            "target_requires": ["locator_type"],
            "expected_old_requires": ["old_excerpt"],
        },
        "fallback_rule": "If you cannot produce a valid EditPlanV0, return move=mark_blocked with a clear reason. Do not return malformed apply_edit_plan.",
        "attempt": int(attempt or 0),
        "max_attempts": int(max_attempts or 0),
    }
    if isinstance(injection_context, dict) and injection_context:
        payload["injection_context"] = injection_context
        if bool(injection_context.get("has_answered_unintegrated_ticket")):
            payload["instruction"] = (
                "Active binding answered_unintegrated human_resolution_ticket is present. "
                "Return a valid move object that addresses integration directly."
            )
    return json.dumps(payload, ensure_ascii=False)
