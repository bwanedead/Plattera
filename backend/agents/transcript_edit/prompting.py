from __future__ import annotations

import json
from typing import Any


def build_planner_system_message() -> str:
    # Trunk covers: "Return only valid JSON. Never output prose or markdown." + "Be faithful to source material."
    # Branch covers: "Mapping-blocking unresolved items are the highest priority focus."
    return (
        "You are a legal transcript edit planner. "
        "Your mission is to drive the transcript toward zero mapping-critical inaccuracies for downstream deed-to-IR and mapping loops. "
        "Propose a bounded EditPlanV0 JSON object only. "
        "Prioritize sanity and avoid speculative edits. "
        "Never treat unresolved bearing/range/tie-distance conflicts as done; plans must explicitly target unresolved conflicts when evidence supports a safe edit. "
        "Do not propose purely cosmetic formatting edits (spacing, punctuation, symbol variants) unless meaning changes. "
        "Prefer localized normalization edits first. "
        "If a finding indicates numeric/PLSS inconsistency and context provides a clear dominant value, "
        "you may propose a localized semantic correction with review_required=true. "
        "Each op must include drift-safe expected_old.old_excerpt from verbatim transcript text. "
        "Prefer anchors locator; use offsets only when anchors are unreliable. "
        "Do not produce cross-section edits unless strictly necessary. "
        "If findings do not justify changes, return an empty ops list with rationale."
    )


def build_planner_user_message(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    findings_summary: dict[str, Any],
    top_findings: list[dict[str, Any]],
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any],
    candidate_disagreement_hints: dict[str, Any],
    mapping_priority_focus: dict[str, Any],
) -> str:
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
        "top_findings": top_findings,
        "span_context": span_context,
        "image_verification": image_verification,
        "candidate_disagreement_hints": candidate_disagreement_hints,
        "mapping_priority_focus": mapping_priority_focus,
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
        "note": "If no safe edit is justified, return ops=[] with rationale.",
    }
    return json.dumps(payload, ensure_ascii=False)


def build_focus_resolver_system_message() -> str:
    return (
        "You are a transcript-edit focus resolver. "
        "Return one bounded JSON move object for the current focus item. "
        "The runtime preselects the focus decision_key; do not switch focus to any other item. "
        "Allowed move values: apply_edit_plan, request_human_feedback, gather_more_evidence, mark_blocked, mark_resolved_no_edit, propose_blocker_updates. "
        "If move=apply_edit_plan, include a valid EditPlanV0 in edit_plan. "
        "If move=propose_blocker_updates, include blocker_updates[] with structured operations only (add/update/resolve/supersede). "
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
        "Prioritize removing open mapping blockers before optional work; when focused_blocker_feedback_pair.ready_for_resolution=true, your next move must directly integrate or safely escalate that blocker-ticket pair. "
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
        "Always include decision_key, move, reason, and iteration_summary."
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
    payload = {
        "task": "Choose one next move for this focus-cycle item.",
        "allowed_moves": [
            "apply_edit_plan",
            "request_human_feedback",
            "gather_more_evidence",
            "mark_blocked",
            "mark_resolved_no_edit",
            "propose_blocker_updates",
        ],
        "required_fields": ["decision_key", "move", "reason", "iteration_summary"],
        "focus_packet": focus_packet,
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
        ],
        "move_contract": {
            "apply_edit_plan_requires": ["edit_plan"],
            "request_human_feedback_requires": ["feedback_prompt"],
            "gather_more_evidence_requires": ["evidence_request"],
            "mark_blocked_requires": ["reason"],
            "mark_resolved_no_edit_requires": ["reason"],
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
