from __future__ import annotations

from typing import Any

from tooling.mapping.transcription_edit.contracts import EditPlanV0

from .plan_interpretation import load_working_transcript_text, validate_edit_plan_directionality
from .planner import TranscriptEditPlanPlanner, _resolver_injection_context

_RESOLVER_RAW_OUTPUT_CAPTURE_MAX_CHARS = 4000


def resolve_focus_move(
    *,
    focus_packet: dict[str, Any],
    planner_client: TranscriptEditPlanPlanner,
    model: str,
    findings_summary: dict[str, Any],
    planning_findings: list[dict[str, Any]],
    max_invalid_plan_attempts: int,
    validation_mode: str = "off",
    run_link_id: str = "",
    mission_objective: str = "",
) -> dict[str, Any]:
    decision_key = str(focus_packet.get("decision_key") or "").strip().lower()
    ledger_item = focus_packet.get("ledger_item") if isinstance(focus_packet.get("ledger_item"), dict) else {}
    closure_requirement = focus_packet.get("closure_requirement") if isinstance(focus_packet.get("closure_requirement"), dict) else {}
    feedback = focus_packet.get("feedback") if isinstance(focus_packet.get("feedback"), dict) else None
    source_transcript_ref = str(focus_packet.get("source_transcript_ref") or "").strip()
    source_transcript_hash = str(focus_packet.get("source_transcript_hash") or "").strip()
    span_context = focus_packet.get("span_context") if isinstance(focus_packet.get("span_context"), list) else []
    image_verification = focus_packet.get("image_verification") if isinstance(focus_packet.get("image_verification"), dict) else {}
    answered_ticket = _active_answered_unintegrated_ticket(
        focus_packet=focus_packet,
        decision_key=decision_key,
    )

    if not decision_key or not source_transcript_ref or not source_transcript_hash:
        return {
            "decision_key": decision_key or "unknown",
            "move": "mark_blocked",
            "reason": "focus_packet_incomplete",
            "iteration_summary": "Focus packet missing required transcript context; cannot continue safely.",
        }

    is_harness_emergent_focus = str(decision_key).startswith("harness:emergent:")
    if is_harness_emergent_focus:
        awi = focus_packet.get("active_emergent_board_item") if isinstance(focus_packet.get("active_emergent_board_item"), dict) else {}
        if not awi:
            return {
                "decision_key": decision_key,
                "move": "mark_blocked",
                "reason": "harness_emergent_board_row_missing",
                "iteration_summary": "Harness-emergent focus is set but the board row is missing from the packet.",
            }
        bstate = str(awi.get("state") or "").strip().lower()
        if bstate in {"resolved", "superseded"}:
            return {
                "decision_key": decision_key,
                "move": "mark_resolved_no_edit",
                "reason": "harness_emergent_board_item_terminal",
                "iteration_summary": "Harness-emergent board item is resolved or superseded.",
            }
    else:
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

    feedback_summary = feedback if isinstance(feedback, dict) else None
    focus_payload = {
        **focus_packet,
        "findings_summary": findings_summary if isinstance(findings_summary, dict) else {},
        "planning_findings": [f for f in planning_findings if isinstance(f, dict)][:12],
        "feedback": feedback_summary,
        "validation_mode": validation_mode,
    }
    try:
        move_payload, move_reason, _raw_move = planner_client.propose_focus_move(
            model=model,
            focus_packet=focus_payload,
            max_attempts=max_invalid_plan_attempts,
            run_link_id=run_link_id,
            mission_objective=mission_objective,
        )
    except Exception as exc:
        move_payload = None
        move_reason = f"resolver_exception:{type(exc).__name__}"
        _raw_move = ""
    if isinstance(move_payload, dict):
        out = dict(move_payload)
        out.setdefault("decision_key", decision_key)
        out.setdefault("reason", f"resolver_move:{move_reason}")
        out.setdefault("iteration_summary", f"Focused on {decision_key}.")
        out.setdefault("feedback_prompt", None)
        out.setdefault("evidence_request", None)
        out.setdefault("blocker_updates", None)
        out.setdefault("iteration_understanding", None)
        out.setdefault("closure_update_hint", None)
        raw_excerpt = str(_raw_move or "").strip()
        if raw_excerpt:
            out["resolver_raw_output_excerpt"] = raw_excerpt[:_RESOLVER_RAW_OUTPUT_CAPTURE_MAX_CHARS]
        move = str(out.get("move") or "").strip().lower()
        if move == "apply_edit_plan":
            payload = out.get("edit_plan") if isinstance(out.get("edit_plan"), dict) else {}
            ops = payload.get("ops") if isinstance(payload, dict) else []
            if not (isinstance(ops, list) and len(ops) > 0):
                return {
                    "decision_key": decision_key,
                    "move": "gather_more_evidence",
                    "reason": "resolver_apply_without_ops",
                    "iteration_summary": f"Resolver proposed apply_edit_plan without safe ops for {decision_key}.",
                    "feedback_prompt": None,
                    "evidence_request": None,
                    "blocker_updates": None,
                    "closure_update_hint": None,
                }
            inj = _resolver_injection_context(focus_packet=focus_packet, decision_key=decision_key)
            try:
                plan_obj = EditPlanV0.model_validate(payload)
                ttext = load_working_transcript_text(source_transcript_ref)
                if ttext.strip():
                    ok, direction_reason = validate_edit_plan_directionality(
                        plan=plan_obj,
                        transcript_text=ttext,
                        feedback=feedback_summary,
                        injection_context=inj,
                    )
                    if not ok:
                        return {
                            "decision_key": decision_key,
                            "move": "mark_blocked",
                            "reason": f"resolver_edit_plan_directionality:{direction_reason}",
                            "iteration_summary": (
                                f"Edit plan failed directionality checks ({direction_reason}) for {decision_key}."
                            ),
                            "feedback_prompt": None,
                            "evidence_request": None,
                            "blocker_updates": None,
                            "closure_update_hint": None,
                        }
            except Exception:
                pass
        return out

    if str(move_reason).startswith(("resolver_invalid", "resolver_exception", "resolver_api_error")):
        outcome = {
            "decision_key": decision_key,
            "move": "mark_blocked",
            "reason": f"resolver_move_invalid:{move_reason}",
            "iteration_summary": f"Resolver failed to return a valid move for {decision_key}.",
            "feedback_prompt": None,
            "evidence_request": None,
            "blocker_updates": None,
            "closure_update_hint": None,
        }
        if isinstance(answered_ticket, dict):
            outcome["post_feedback_ticket_state"] = "answered_unintegrated"
            outcome["post_feedback_ticket_id"] = str(answered_ticket.get("ticket_id") or "").strip() or None
        outcome["resolver_invalid_diagnostic"] = {
            "decision_key": decision_key,
            "raw_output_excerpt": str(_raw_move or "")[:_RESOLVER_RAW_OUTPUT_CAPTURE_MAX_CHARS] or None,
            "reason": str(move_reason or ""),
        }
        return outcome

    if feedback_summary:
        return {
            "decision_key": decision_key,
            "move": "mark_blocked",
            "reason": f"resolver_no_move_after_feedback:{move_reason}",
            "iteration_summary": f"Feedback was received for {decision_key}, but resolver did not produce a usable move.",
            "feedback_prompt": None,
            "evidence_request": None,
            "blocker_updates": None,
            "closure_update_hint": None,
        }

    return {
        "decision_key": decision_key,
        "move": "request_human_feedback",
        "reason": f"resolver_needs_feedback:{move_reason}",
        "iteration_summary": f"Further human feedback is needed to resolve {decision_key}.",
        "feedback_prompt": None,
        "evidence_request": None,
        "blocker_updates": None,
        "closure_update_hint": None,
    }


def _active_answered_unintegrated_ticket(
    *,
    focus_packet: dict[str, Any],
    decision_key: str,
) -> dict[str, Any] | None:
    rows = (
        [row for row in list(focus_packet.get("external_context_injections") or []) if isinstance(row, dict)]
        if isinstance(focus_packet, dict)
        else []
    )
    key = str(decision_key or "").strip().lower()
    for row in rows:
        if str(row.get("type") or "").strip().lower() != "human_resolution_ticket":
            continue
        if str(row.get("decision_key") or "").strip().lower() != key:
            continue
        if str(row.get("lifecycle_state") or "").strip().lower() != "answered_unintegrated":
            continue
        return dict(row)
    return None


