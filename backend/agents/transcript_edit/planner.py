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

SUPPORTED_IMAGE_EVIDENCE_MODES = {"select_region", "refine_region", "verify_region", "locate"}
KNOWN_IMAGE_EVIDENCE_DICT_TARGET_FIELDS = {
    "region_ref",
    "context_ref",
    "crop_box_pixels",
    "crop_box_normalized",
    "grid_selection",
    "grid_spec",
}


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
        injection_context = _resolver_injection_context(focus_packet=focus_packet, decision_key=decision_key)
        raw_content = ""
        last_error = "resolver_invalid_response"

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
                completion = client.chat.completions.create(**params)
            except Exception as exc:
                last_error = f"resolver_api_error:{type(exc).__name__}"
                user_msg = build_focus_resolver_repair_user_message(
                    error_reason=last_error,
                    raw_content="",
                    decision_key=decision_key,
                    injection_context=injection_context,
                    attempt=attempt,
                    max_attempts=max_attempts,
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
                    injection_context=injection_context,
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
                continue
            try:
                parsed = json.loads(raw_content)
                if not isinstance(parsed, dict):
                    last_error = "resolver_non_object_json"
                    raise ValueError(last_error)
            except Exception as exc:
                message = str(exc).strip()
                last_error = (
                    f"resolver_invalid:{type(exc).__name__}:{message[:120]}"
                    if message
                    else f"resolver_invalid:{type(exc).__name__}"
                )
                user_msg = build_focus_resolver_repair_user_message(
                    error_reason=last_error,
                    raw_content=raw_content,
                    decision_key=decision_key,
                    injection_context=injection_context,
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
                continue
            try:
                validated = _coerce_focus_move(
                    parsed=parsed,
                    decision_key=decision_key,
                    source_transcript_ref=str(focus_packet.get("source_transcript_ref") or ""),
                    source_transcript_hash=str(focus_packet.get("source_transcript_hash") or ""),
                )
                return validated, "ok", raw_content
            except Exception as exc:
                message = str(exc).strip()
                last_error = (
                    f"resolver_invalid:{type(exc).__name__}:{message[:120]}"
                    if message
                    else f"resolver_invalid:{type(exc).__name__}"
                )
                fallback = _post_feedback_invalid_apply_fallback(
                    parsed=parsed,
                    decision_key=decision_key,
                    injection_context=injection_context,
                )
                if isinstance(fallback, dict):
                    return fallback, "ok_post_feedback_fallback", raw_content
                user_msg = build_focus_resolver_repair_user_message(
                    error_reason=last_error,
                    raw_content=raw_content,
                    decision_key=decision_key,
                    injection_context=injection_context,
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
        return None, last_error, raw_content


def _resolver_injection_context(*, focus_packet: dict[str, Any], decision_key: str) -> dict[str, Any]:
    rows = (
        [row for row in list(focus_packet.get("external_context_injections") or []) if isinstance(row, dict)]
        if isinstance(focus_packet, dict)
        else []
    )
    key = str(decision_key or "").strip().lower()
    answered = next(
        (
            row
            for row in rows
            if str(row.get("type") or "").strip().lower() == "human_resolution_ticket"
            and str(row.get("decision_key") or "").strip().lower() == key
            and str(row.get("lifecycle_state") or "").strip().lower() == "answered_unintegrated"
        ),
        None,
    )
    if not isinstance(answered, dict):
        return {"has_answered_unintegrated_ticket": False}
    payload = answered.get("payload") if isinstance(answered.get("payload"), dict) else {}
    return {
        "has_answered_unintegrated_ticket": True,
        "ticket_id": str(answered.get("ticket_id") or "").strip() or None,
        "decision_key": key,
        "lifecycle_state": "answered_unintegrated",
        "strength": str(answered.get("strength") or "").strip().lower() or None,
        "normalized_answer_summary": str(payload.get("normalized_answer_summary") or "").strip() or None,
        "selected_choice": str(payload.get("selected_choice") or "").strip() or None,
    }


def _post_feedback_invalid_apply_fallback(
    *,
    parsed: dict[str, Any],
    decision_key: str,
    injection_context: dict[str, Any],
) -> dict[str, Any] | None:
    if not bool(injection_context.get("has_answered_unintegrated_ticket")):
        return None
    move = str(parsed.get("move") or "").strip().lower()
    if move != "apply_edit_plan":
        return None
    ticket_id = str(injection_context.get("ticket_id") or "").strip() or None
    return {
        "decision_key": decision_key,
        "move": "mark_blocked",
        "reason": "blocked_no_safe_integration_after_feedback:invalid_apply_payload",
        "edit_plan": None,
        "feedback_prompt": None,
        "evidence_request": None,
        "closure_update_hint": None,
        "iteration_summary": (
            "Human answer is present, but resolver apply payload was invalid; blocked pending safe integration decision."
        ),
        "post_feedback_ticket_state": "answered_unintegrated",
        "post_feedback_ticket_id": ticket_id,
    }


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
        if evidence_kind not in {"open_spans", "image_verify", "image_evidence", "retrieve_dependency_evidence"}:
            raise ValueError("invalid_evidence_request_kind")
        evidence_key = str(evidence.get("decision_key") or out["decision_key"]).strip().lower()
        if evidence_key != out["decision_key"]:
            raise ValueError("evidence_request_decision_key_mismatch")
        target = evidence.get("target") if isinstance(evidence.get("target"), dict) else {}
        evidence_mode = str(evidence.get("mode") or "").strip().lower()
        if evidence_kind == "image_evidence":
            evidence_mode, target, normalize_error = _normalize_image_evidence_shape(
                mode=evidence_mode,
                target=target,
            )
            if normalize_error is not None:
                raise ValueError(normalize_error)
            if evidence_mode not in SUPPORTED_IMAGE_EVIDENCE_MODES:
                raise ValueError("invalid_image_evidence_mode")
        out["evidence_request"] = {
            "kind": evidence_kind,
            "mode": evidence_mode or None,
            "decision_key": evidence_key,
            "reason": str(evidence.get("reason") or "").strip()[:240],
            "target": {
                "span_ids": [str(v).strip() for v in list(target.get("span_ids") or []) if str(v).strip()][:8],
                "expected_fields": [str(v).strip().lower() for v in list(target.get("expected_fields") or []) if str(v).strip()][:6],
                "region_ref": target.get("region_ref") if isinstance(target.get("region_ref"), dict) else None,
                "context_ref": target.get("context_ref") if isinstance(target.get("context_ref"), dict) else None,
                "query": str(target.get("query") or "").strip()[:320] or None,
                "expected_text": str(target.get("expected_text") or "").strip()[:180] or None,
                "anchor_hint": str(target.get("anchor_hint") or "").strip()[:220] or None,
                "source_image_ref": str(target.get("source_image_ref") or "").strip() or None,
                "crop_box_pixels": (
                    dict(target.get("crop_box_pixels"))
                    if isinstance(target.get("crop_box_pixels"), dict)
                    else None
                ),
                "crop_box_normalized": (
                    dict(target.get("crop_box_normalized"))
                    if isinstance(target.get("crop_box_normalized"), dict)
                    else None
                ),
                "grid_selection": (
                    dict(target.get("grid_selection"))
                    if isinstance(target.get("grid_selection"), dict)
                    else None
                ),
                "grid_spec": (
                    dict(target.get("grid_spec"))
                    if isinstance(target.get("grid_spec"), dict)
                    else None
                ),
                "zoom_factor": target.get("zoom_factor"),
                "transform": str(target.get("transform") or "").strip().lower() or None,
                "amount": target.get("amount"),
            },
        }
    if isinstance(parsed.get("closure_update_hint"), dict):
        out["closure_update_hint"] = dict(parsed.get("closure_update_hint"))
    return out


def _normalize_image_evidence_shape(
    *,
    mode: str,
    target: dict[str, Any],
) -> tuple[str, dict[str, Any], str | None]:
    normalized_mode = str(mode or "").strip().lower()
    normalized_target = dict(target) if isinstance(target, dict) else {}
    target_mode_raw = str(normalized_target.get("mode") or "").strip().lower()
    target_mode = target_mode_raw or ""
    if target_mode and target_mode not in SUPPORTED_IMAGE_EVIDENCE_MODES:
        return "", {}, "image_evidence_target_mode_invalid"
    operation_keys = [
        key
        for key in SUPPORTED_IMAGE_EVIDENCE_MODES
        if isinstance(normalized_target.get(key), dict)
    ]
    if len(operation_keys) > 1:
        return "", {}, "image_evidence_target_mode_ambiguous"
    unknown_nested_ops = [
        str(key).strip().lower()
        for key, value in normalized_target.items()
        if isinstance(value, dict)
        and str(key).strip().lower() not in SUPPORTED_IMAGE_EVIDENCE_MODES
        and str(key).strip().lower() not in KNOWN_IMAGE_EVIDENCE_DICT_TARGET_FIELDS
    ]
    if unknown_nested_ops:
        return "", {}, "image_evidence_nested_operation_invalid"
    operation_mode = operation_keys[0] if operation_keys else ""
    mode_sources = [m for m in (normalized_mode, target_mode, operation_mode) if m]
    if len(set(mode_sources)) > 1:
        return "", {}, "image_evidence_mode_conflict"
    canonical_mode = mode_sources[0] if mode_sources else ""
    if operation_mode:
        nested_target = normalized_target.get(operation_mode)
        if not isinstance(nested_target, dict):
            return "", {}, "image_evidence_nested_operation_invalid"
        extra_keys = [
            str(key).strip().lower()
            for key, value in normalized_target.items()
            if str(key).strip().lower() not in {operation_mode, "mode"}
            and value not in (None, "", [], {})
        ]
        if extra_keys:
            return "", {}, "image_evidence_target_mode_ambiguous"
        nested_mode, nested_target_out = _normalize_refine_region_crop_shorthand(
            mode=canonical_mode,
            target=dict(nested_target),
        )
        return nested_mode, nested_target_out, None
    if target_mode:
        normalized_target = {
            key: value
            for key, value in normalized_target.items()
            if str(key).strip().lower() != "mode"
        }
    canonical_mode, normalized_target = _normalize_refine_region_crop_shorthand(
        mode=canonical_mode,
        target=normalized_target,
    )
    return canonical_mode, normalized_target, None


def _normalize_refine_region_crop_shorthand(*, mode: str, target: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    canonical_mode = str(mode or "").strip().lower()
    normalized_target = dict(target) if isinstance(target, dict) else {}
    if canonical_mode != "refine_region":
        return canonical_mode, normalized_target
    if isinstance(normalized_target.get("region_ref"), dict):
        return canonical_mode, normalized_target
    selector_count = sum(
        (
            1 if isinstance(normalized_target.get("crop_box_pixels"), dict) else 0,
            1 if isinstance(normalized_target.get("crop_box_normalized"), dict) else 0,
            1 if isinstance(normalized_target.get("grid_selection"), dict) else 0,
        )
    )
    transform = str(normalized_target.get("transform") or "").strip().lower()
    amount = normalized_target.get("amount")
    has_amount = amount not in (None, "")
    if selector_count == 1 and not transform and not has_amount:
        return "select_region", normalized_target
    return canonical_mode, normalized_target
