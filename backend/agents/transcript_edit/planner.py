from __future__ import annotations

import json
from typing import Any

from services.llm.openai import OpenAIService
from transcript_edit.contracts import EditPlanV0

from .prompting import (
    build_focus_resolver_repair_user_message,
    build_focus_resolver_system_message,
    build_focus_resolver_user_message,
    build_plan_repair_user_message,
    build_planner_system_message,
    build_planner_user_message,
)


class TranscriptEditPlanPlanner:
    def __init__(self, service: OpenAIService | None = None) -> None:
        self._service = service or OpenAIService()

    def propose_plan(
        self,
        *,
        model: str,
        source_transcript_ref: str,
        source_transcript_hash: str,
        findings_summary: dict[str, Any],
        top_findings: list[dict[str, Any]],
        span_context: list[dict[str, Any]],
        image_verification: dict[str, Any] | None,
        candidate_disagreement_hints: dict[str, Any] | None,
        mapping_priority_focus: dict[str, Any] | None,
        max_attempts: int,
    ) -> tuple[EditPlanV0 | None, str, str]:
        if not self._service.is_available() or getattr(self._service, "client", None) is None:
            return None, "planner_unavailable", ""
        api_model = self._service.models.get(model, {}).get("api_model_name", model)
        client = self._service.client

        system_msg = build_planner_system_message()
        user_msg = build_planner_user_message(
            source_transcript_ref=source_transcript_ref,
            source_transcript_hash=source_transcript_hash,
            findings_summary=findings_summary,
            top_findings=top_findings,
            span_context=span_context,
            image_verification=image_verification or {},
            candidate_disagreement_hints=candidate_disagreement_hints or {},
            mapping_priority_focus=mapping_priority_focus or {},
        )
        raw_content = ""
        last_error = "planner_invalid_response"
        for attempt in range(1, max_attempts + 1):
            params: dict[str, Any] = {
                "model": api_model,
                "messages": [
                    {"role": "developer", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                "response_format": {"type": "json_object"},
            }
            if "gpt-5" in str(api_model):
                params["max_completion_tokens"] = 8000
                params["reasoning_effort"] = "medium"
            else:
                params["max_tokens"] = 4000
                params["temperature"] = 0
            try:
                completion = client.chat.completions.create(
                    **params,
                )
            except Exception as exc:
                last_error = f"planner_api_error:{type(exc).__name__}"
                user_msg = build_plan_repair_user_message(
                    error_reason=last_error,
                    raw_content="",
                    source_transcript_ref=source_transcript_ref,
                    source_transcript_hash=source_transcript_hash,
                )
                continue
            message = completion.choices[0].message if completion.choices else None
            content = message.content if message is not None else None
            raw_content = content if isinstance(content, str) else ""
            if not raw_content.strip():
                last_error = "planner_empty_response"
                user_msg = build_plan_repair_user_message(
                    error_reason=last_error,
                    raw_content=raw_content,
                    source_transcript_ref=source_transcript_ref,
                    source_transcript_hash=source_transcript_hash,
                )
                continue
            try:
                parsed = json.loads(raw_content)
                if not isinstance(parsed, dict):
                    last_error = "planner_non_object_json"
                    raise ValueError(last_error)
                parsed.setdefault("source_transcript_ref", source_transcript_ref)
                parsed.setdefault("source_transcript_hash", source_transcript_hash)
                plan = EditPlanV0.model_validate(parsed)
                return plan, "ok", raw_content
            except Exception as exc:
                last_error = f"plan_invalid:{type(exc).__name__}"
                user_msg = build_plan_repair_user_message(
                    error_reason=last_error,
                    raw_content=raw_content,
                    source_transcript_ref=source_transcript_ref,
                    source_transcript_hash=source_transcript_hash,
                )
        return None, last_error, raw_content

    def propose_focus_move(
        self,
        *,
        model: str,
        focus_packet: dict[str, Any],
        max_attempts: int,
    ) -> tuple[dict[str, Any] | None, str, str]:
        if not self._service.is_available() or getattr(self._service, "client", None) is None:
            return None, "resolver_unavailable", ""
        api_model = self._service.models.get(model, {}).get("api_model_name", model)
        client = self._service.client

        system_msg = build_focus_resolver_system_message()
        user_msg = build_focus_resolver_user_message(focus_packet=focus_packet)
        decision_key = str(focus_packet.get("decision_key") or "decision")
        raw_content = ""
        last_error = "resolver_invalid_response"

        for _attempt in range(1, max_attempts + 1):
            params: dict[str, Any] = {
                "model": api_model,
                "messages": [
                    {"role": "developer", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                "response_format": {"type": "json_object"},
            }
            if "gpt-5" in str(api_model):
                params["max_completion_tokens"] = 8000
                params["reasoning_effort"] = "medium"
            else:
                params["max_tokens"] = 4000
                params["temperature"] = 0
            try:
                completion = client.chat.completions.create(**params)
            except Exception as exc:
                last_error = f"resolver_api_error:{type(exc).__name__}"
                user_msg = build_focus_resolver_repair_user_message(
                    error_reason=last_error,
                    raw_content="",
                    decision_key=decision_key,
                )
                continue
            message = completion.choices[0].message if completion.choices else None
            content = message.content if message is not None else None
            raw_content = content if isinstance(content, str) else ""
            if not raw_content.strip():
                last_error = "resolver_empty_response"
                user_msg = build_focus_resolver_repair_user_message(
                    error_reason=last_error,
                    raw_content=raw_content,
                    decision_key=decision_key,
                )
                continue
            try:
                parsed = json.loads(raw_content)
                if not isinstance(parsed, dict):
                    last_error = "resolver_non_object_json"
                    raise ValueError(last_error)
                validated = _coerce_focus_move(
                    parsed=parsed,
                    decision_key=decision_key,
                    source_transcript_ref=str(focus_packet.get("source_transcript_ref") or ""),
                    source_transcript_hash=str(focus_packet.get("source_transcript_hash") or ""),
                )
                return validated, "ok", raw_content
            except Exception as exc:
                last_error = f"resolver_invalid:{type(exc).__name__}"
                user_msg = build_focus_resolver_repair_user_message(
                    error_reason=last_error,
                    raw_content=raw_content,
                    decision_key=decision_key,
                )
        return None, last_error, raw_content


def _coerce_focus_move(
    *,
    parsed: dict[str, Any],
    decision_key: str,
    source_transcript_ref: str,
    source_transcript_hash: str,
) -> dict[str, Any]:
    allowed_moves = {
        "apply_edit_plan",
        "request_human_feedback",
        "gather_more_evidence",
        "mark_blocked",
        "mark_resolved_no_edit",
    }
    move = str(parsed.get("move") or "").strip().lower()
    if move not in allowed_moves:
        raise ValueError("invalid_move")
    out: dict[str, Any] = {
        "decision_key": str(parsed.get("decision_key") or decision_key).strip().lower() or decision_key,
        "move": move,
        "reason": str(parsed.get("reason") or "").strip() or "resolver_reason_missing",
        "edit_plan": None,
        "feedback_prompt": None,
        "evidence_request": None,
        "closure_update_hint": None,
        "iteration_summary": str(parsed.get("iteration_summary") or "").strip() or "Focus move selected.",
    }
    if move == "apply_edit_plan":
        payload = parsed.get("edit_plan")
        if not isinstance(payload, dict):
            raise ValueError("missing_edit_plan_for_apply_move")
        payload.setdefault("source_transcript_ref", source_transcript_ref)
        payload.setdefault("source_transcript_hash", source_transcript_hash)
        plan = EditPlanV0.model_validate(payload)
        out["edit_plan"] = plan.model_dump(mode="json")
    if move == "request_human_feedback":
        prompt = parsed.get("feedback_prompt")
        if isinstance(prompt, dict):
            out["feedback_prompt"] = {
                "line1": str(prompt.get("line1") or "").strip() or "Human feedback required.",
                "line2": str(prompt.get("line2") or "").strip() or "Please choose the best-supported value.",
                "choices": [str(v).strip() for v in list(prompt.get("choices") or []) if str(v).strip()][:6],
            }
    if move == "gather_more_evidence":
        evidence = parsed.get("evidence_request")
        if not isinstance(evidence, dict):
            raise ValueError("missing_evidence_request_for_gather_move")
        evidence_kind = str(evidence.get("kind") or "").strip().lower()
        if evidence_kind not in {"open_spans", "image_verify", "retrieve_dependency_evidence"}:
            raise ValueError("invalid_evidence_request_kind")
        evidence_key = str(evidence.get("decision_key") or out["decision_key"]).strip().lower()
        if evidence_key != out["decision_key"]:
            raise ValueError("evidence_request_decision_key_mismatch")
        target = evidence.get("target") if isinstance(evidence.get("target"), dict) else {}
        out["evidence_request"] = {
            "kind": evidence_kind,
            "decision_key": evidence_key,
            "reason": str(evidence.get("reason") or "").strip()[:240],
            "target": {
                "span_ids": [str(v).strip() for v in list(target.get("span_ids") or []) if str(v).strip()][:8],
                "expected_fields": [str(v).strip().lower() for v in list(target.get("expected_fields") or []) if str(v).strip()][:6],
            },
        }
    if isinstance(parsed.get("closure_update_hint"), dict):
        out["closure_update_hint"] = dict(parsed.get("closure_update_hint"))
    return out
