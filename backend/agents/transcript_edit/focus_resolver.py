from __future__ import annotations

from typing import Any

from .planner import TranscriptEditPlanPlanner


def resolve_focus_move(
    *,
    focus_packet: dict[str, Any],
    planner_client: TranscriptEditPlanPlanner,
    model: str,
    findings_summary: dict[str, Any],
    planning_findings: list[dict[str, Any]],
    max_invalid_plan_attempts: int,
) -> dict[str, Any]:
    decision_key = str(focus_packet.get("decision_key") or "").strip().lower()
    ledger_item = focus_packet.get("ledger_item") if isinstance(focus_packet.get("ledger_item"), dict) else {}
    closure_requirement = focus_packet.get("closure_requirement") if isinstance(focus_packet.get("closure_requirement"), dict) else {}
    feedback = focus_packet.get("feedback") if isinstance(focus_packet.get("feedback"), dict) else None
    source_transcript_ref = str(focus_packet.get("source_transcript_ref") or "").strip()
    source_transcript_hash = str(focus_packet.get("source_transcript_hash") or "").strip()
    span_context = focus_packet.get("span_context") if isinstance(focus_packet.get("span_context"), list) else []
    image_verification = focus_packet.get("image_verification") if isinstance(focus_packet.get("image_verification"), dict) else {}

    if not decision_key or not source_transcript_ref or not source_transcript_hash:
        return {
            "decision_key": decision_key or "unknown",
            "move": "mark_blocked",
            "reason": "focus_packet_incomplete",
            "iteration_summary": "Focus packet missing required transcript context; cannot continue safely.",
        }

    state = str(ledger_item.get("state") or "unknown").strip().lower()
    mapping_blocking = bool(
        closure_requirement.get("mapping_blocking", ledger_item.get("blocking"))
    )
    unresolved = state in {"unknown", "candidate_found", "disputed", "accepted_with_risk"}

    if not (mapping_blocking and unresolved):
        return {
            "decision_key": decision_key,
            "move": "mark_resolved_no_edit",
            "reason": "focus_item_not_mapping_blocking_unresolved",
            "iteration_summary": "Focused item is no longer mapping-blocking unresolved.",
        }

    feedback_summary = {}
    if isinstance(feedback, dict):
        feedback_summary = {
            "decision_key": feedback.get("decision_key"),
            "selected_value": feedback.get("selected_value"),
            "note": feedback.get("note"),
        }
    mapping_priority_focus = {
        "decision_key": decision_key,
        "focus_state": state,
        "focus_reason": "human_feedback_available" if feedback_summary else "ledger_priority",
        "feedback": feedback_summary,
    }

    try:
        plan, plan_reason, _raw_plan = planner_client.propose_plan(
            model=model,
            source_transcript_ref=source_transcript_ref,
            source_transcript_hash=source_transcript_hash,
            findings_summary=findings_summary,
            top_findings=[f for f in planning_findings if isinstance(f, dict)],
            span_context=[s for s in span_context if isinstance(s, dict)],
            image_verification=image_verification,
            candidate_disagreement_hints={"human_feedback": feedback_summary} if feedback_summary else {},
            mapping_priority_focus=mapping_priority_focus,
            max_attempts=max_invalid_plan_attempts,
        )
    except Exception as exc:
        plan = None
        plan_reason = f"planner_exception:{type(exc).__name__}"
    if plan is not None:
        payload = plan.model_dump(mode="json")
        ops = payload.get("ops") if isinstance(payload, dict) else []
        if isinstance(ops, list) and len(ops) > 0:
            return {
                "decision_key": decision_key,
                "move": "apply_edit_plan",
                "reason": f"resolver_planner:{plan_reason}",
                "edit_plan": payload,
                "iteration_summary": f"Applying semantic plan for {decision_key}.",
            }
        return {
            "decision_key": decision_key,
            "move": "gather_more_evidence",
            "reason": f"resolver_no_ops:{plan_reason}",
            "iteration_summary": f"Planner returned no safe edit ops for {decision_key}; continuing evidence loop.",
        }

    if str(plan_reason).startswith(("plan_invalid", "planner_invalid", "planner_exception")):
        return {
            "decision_key": decision_key,
            "move": "mark_blocked",
            "reason": f"resolver_plan_invalid:{plan_reason}",
            "iteration_summary": f"Planner failed to produce a valid plan for {decision_key}.",
        }

    if feedback_summary:
        return {
            "decision_key": decision_key,
            "move": "mark_blocked",
            "reason": f"resolver_feedback_no_plan:{plan_reason}",
            "iteration_summary": f"Feedback was received for {decision_key}, but no safe semantic plan was available.",
        }

    return {
        "decision_key": decision_key,
        "move": "request_human_feedback",
        "reason": f"resolver_needs_feedback:{plan_reason}",
        "iteration_summary": f"Further human feedback is needed to resolve {decision_key}.",
    }
