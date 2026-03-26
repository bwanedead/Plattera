from __future__ import annotations

import hashlib
import logging
from typing import Any

from agent_kernel.models import KernelStepRequest

from harness.orchestration_kernel.contracts import MoveDecision, MoveExecutionPlan, OrchestratorContext

from .execution_action_ids import TX_AUDIT_TRANSCRIPT, TX_OPEN_TRANSCRIPT_SPANS, TX_VERIFY_TRANSCRIPT_WITH_IMAGE
from .evidence_executor import normalize_evidence_request
from .evidence_runtime import cache_image_verification_for_key, cache_visual_evidence_for_key, run_image_evidence_mode
from .focus_runtime import recent_image_evidence_attempt_count
from .loop_runtime import idempotency_key as _make_idempotency_key, read_step_outputs_inline

_LOG = logging.getLogger(__name__)


def compile_transcript_edit_execution_support(
    pack: Any,
    context: OrchestratorContext,
    move_decision: MoveDecision,
    *,
    idempotency_prefix: str,
) -> MoveExecutionPlan:
    request = pack._request
    payload = move_decision.domain_move_payload
    focus_key = move_decision.focus_key or ""
    iterations = context.loop_memory.iterations

    if move_decision.move_type == "gather_more_evidence":
        evidence_request = payload.get("evidence_request") if isinstance(payload.get("evidence_request"), dict) else None
        evidence_kind = str((evidence_request or {}).get("kind") or "open_spans").strip().lower()

        _IMAGE_EVIDENCE_KINDS = {"image_evidence", "image_verify"}
        if evidence_kind in _IMAGE_EVIDENCE_KINDS:
            _recent_img_count = recent_image_evidence_attempt_count(
                continuity_log=list(pack._state.continuity_log or []),
                decision_key=focus_key,
            )
            if _recent_img_count >= 2:
                prompt_id = _make_prompt_id(focus_key, iterations)
                pack._state.pending_feedback_prompt_id = prompt_id
                pack._state.pending_feedback_decision_key = focus_key
                pack._state.pending_feedback_prompt = {
                    "prompt_id": prompt_id,
                    "line1": f"Image evidence cap reached for {focus_key!r} ({_recent_img_count} attempts). Human resolution required.",
                    "line2": "Please confirm the correct value for this field.",
                }
                return MoveExecutionPlan(
                    action_type=TX_AUDIT_TRANSCRIPT,
                    action_inputs={"feedback_prompt_id": prompt_id},
                    idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, {}),
                    hitl_intent_flag=True,
                )

        if evidence_kind in _IMAGE_EVIDENCE_KINDS:
            normalized_req, norm_reason = normalize_evidence_request(
                evidence_request=evidence_request,
                decision_key=focus_key,
            )
            if normalized_req is not None:
                _req_id = pack._request_id_prefix

                def _kernel_step_fn(
                    *,
                    session_manager,
                    session_id,
                    prefix,
                    iteration,
                    action_type,
                    inputs,
                    _req_id=_req_id,
                ):
                    return session_manager.step(
                        KernelStepRequest(
                            session_id=session_id,
                            action_type=action_type,
                            inputs=inputs,
                            idempotency_key=_make_idempotency_key(f"{_req_id}:{prefix}", iteration, inputs),
                        )
                    )

                img_result = run_image_evidence_mode(
                    normalized_request=normalized_req,
                    session_manager=context.session_manager,
                    session_id=context.session_id,
                    iteration=iterations,
                    dossier_id=request.dossier_id,
                    source_transcript_ref=pack._state.current_transcript_ref or "",
                    source_image_refs=list(request.source_image_refs or []),
                    model=pack._loop_model,
                    focus_decision_key=focus_key,
                    top_findings=pack._iter_planning_findings,
                    llm_call_seq_start=pack._state.llm_call_seq,
                    progress_cb=pack._progress_cb,
                    latest_visual_evidence=pack._state.visual_evidence_by_decision_key.get(focus_key),
                    step_fn=_kernel_step_fn,
                    read_step_outputs_inline_fn=read_step_outputs_inline,
                )
                if img_result.get("status") == "executed":
                    _visual = img_result.get("image_evidence") or {}
                    if _visual:
                        cache_visual_evidence_for_key(
                            state=pack._state,
                            decision_key=focus_key,
                            visual_evidence=_visual,
                            source_transcript_ref=pack._state.current_transcript_ref,
                            source_transcript_hash=pack._iter_source_hash,
                        )
                        pack._state.evidence_signal_counter += 1
                    _img_verify = img_result.get("image_verification") or {}
                    if _img_verify:
                        cache_image_verification_for_key(
                            state=pack._state,
                            decision_key=focus_key,
                            image_verification=_img_verify,
                            source_transcript_ref=pack._state.current_transcript_ref,
                            source_transcript_hash=pack._iter_source_hash,
                        )
                    if isinstance(img_result.get("latest_refs"), dict):
                        pack._state.latest_refs.update(dict(img_result["latest_refs"]))
                    for _ in range(max(1, int(img_result.get("llm_contacts") or 1))):
                        context.loop_memory.register_llm_contact()
                    return MoveExecutionPlan(
                        action_type=TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
                        action_inputs={},
                        idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, {}),
                        skip_execution=True,
                    )
            else:
                _LOG.warning(
                    "TX_DOMAIN_PACK image_evidence_norm_fail ► request_id=%s focus_key=%s reason=%s",
                    pack._request_id_prefix,
                    focus_key,
                    norm_reason,
                )

        if evidence_kind == "open_spans":
            inputs = {"dossier_id": request.dossier_id, "decision_key": focus_key}
            if pack._state.current_transcript_ref:
                inputs["source_transcript_ref"] = pack._state.current_transcript_ref
            target = (evidence_request or {}).get("target") if isinstance((evidence_request or {}).get("target"), dict) else {}
            span_ids = [str(v) for v in list((target or {}).get("span_ids") or []) if str(v).strip()][:8]
            if span_ids:
                inputs["span_ids"] = span_ids
            return MoveExecutionPlan(
                action_type=TX_OPEN_TRANSCRIPT_SPANS,
                action_inputs=inputs,
                idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, inputs),
            )

        inputs = {"dossier_id": request.dossier_id}
        if pack._state.current_transcript_ref:
            inputs["source_transcript_ref"] = pack._state.current_transcript_ref
        return MoveExecutionPlan(
            action_type=TX_AUDIT_TRANSCRIPT,
            action_inputs=inputs,
            idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, inputs),
        )

    if move_decision.move_type == "request_human_feedback":
        feedback_prompt = payload.get("feedback_prompt") if isinstance(payload.get("feedback_prompt"), dict) else {}
        prompt_id = str(feedback_prompt.get("prompt_id") or _make_prompt_id(focus_key, iterations)).strip()
        pack._state.pending_feedback_prompt_id = prompt_id
        pack._state.pending_feedback_decision_key = focus_key
        pack._state.pending_feedback_prompt = dict(feedback_prompt)
        return MoveExecutionPlan(
            action_type=TX_AUDIT_TRANSCRIPT,
            action_inputs={"feedback_prompt_id": prompt_id},
            idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, {}),
            hitl_intent_flag=True,
        )

    return MoveExecutionPlan(
        action_type=TX_AUDIT_TRANSCRIPT,
        action_inputs={},
        idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, {}),
        skip_execution=True,
    )


def _make_prompt_id(focus_key: str, iteration: int) -> str:
    raw = f"hitl:{focus_key}:{iteration}"
    return "prompt_" + hashlib.sha1(raw.encode()).hexdigest()[:12]
