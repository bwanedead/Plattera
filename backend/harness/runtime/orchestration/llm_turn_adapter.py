"""Generic LLM-backed orchestration adapter — thin semantic bridge only.

Wires together the LLM caller, choose-action prompt builder, parser, and
mechanical observers carried by ``OrchestratorContext``. Pre-choose continuity
compaction lives on the separate ``LlmTurnPreChooseActionParticipant``
lifecycle surface.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

_LOG = logging.getLogger(__name__)

from services.llm.call_options import LlmCallOptions

from collections.abc import Mapping

from ..composition import ComposedTurnInput
from .action_plan_parser import ModelActionParseError, is_repairable_action_plan_error, parse_action_plan_response
from .tool_batch_policy import (
    resolve_domain_action_batch_policy,
    resolve_tool_batch_policies,
)
from .contracts import ActionPlan, OrchestrationAdapter, OrchestratorContext, SharedStateProjection
from .lifecycle import lifecycle_jsonable
from .llm_prompt_builder import (
    build_choose_action_prompt_document,
    build_resume_prompt_document,
    build_state_repair_prompt_document,
    build_turn_recovery_prompt_document,
    jsonable,
    prompt_visible_launch_context,
)
from .llm_turn_lifecycle import (
    emit_prompt_event_observability,
    resolve_choose_action_prompt_mode,
)
from .repair_lane import TextModelCaller, attempt_repair, extract_audit_text
from ..model_failure_classifier import classify_model_failure
from .audit_turn_mechanics import build_host_hydration_before_turn
from .recoverable_turn_failure import RecoverableTurnFailure, is_recoverable_output_failure
from .resumable_model_interruption import ResumableModelInterruption


def _restore_drained_image_evidence(
    context: OrchestratorContext,
    drained: list[dict[str, Any]],
) -> None:
    """Re-queue image pixels drained before a resumable model-call interruption."""
    if not drained:
        return
    pending = context.loop_memory.pending_image_evidence
    context.loop_memory.pending_image_evidence = list(drained) + list(pending)


@dataclass(frozen=True)
class LlmTurnOrchestrationAdapter(OrchestrationAdapter):
    composed_input: ComposedTurnInput
    text_model_caller: TextModelCaller
    model_name: str
    opaque_launch_context: Mapping[str, Any] = field(default_factory=dict)
    continuity_journal_verbatim_keep_n: int = 3

    def initialize(self, context: OrchestratorContext) -> None:
        del context

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        turn_snapshot = _turn_snapshot(self.composed_input)
        ts = time.time()
        prior_ms = context.loop_memory.continuity.mission_state
        prior_rs = context.loop_memory.continuity.resolution_state

        mo = dict(prior_ms.opaque_payload)
        mo["launch_context"] = prompt_visible_launch_context(self.opaque_launch_context)
        mo["turn_snapshot"] = turn_snapshot

        ro = dict(prior_rs.opaque_payload)
        ro["turn_snapshot"] = turn_snapshot

        resolution_state = prior_rs.model_copy(
            update={"opaque_payload": ro, "updated_at_epoch_seconds": ts}
        )
        mission_state = prior_ms.model_copy(
            update={
                "mission_id": context.session_id,
                "session_id": context.session_id,
                "request_id": context.request_id_prefix,
                "loop_family": "orchestration_kernel",
                "updated_at_epoch_seconds": ts,
                "opaque_payload": mo,
                "resolution_state": resolution_state,
            }
        )
        cont_active = context.loop_memory.continuity.active_item_id
        rs_active = resolution_state.active_item_id
        return SharedStateProjection(
            mission_state=mission_state,
            resolution_state=resolution_state,
            latest_refs=dict(context.loop_memory.continuity.latest_refs),
            active_item_id=cont_active if cont_active is not None else rs_active,
        )

    def choose_action(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
    ) -> ActionPlan:
        _t0 = time.time()
        prompt_mode = resolve_choose_action_prompt_mode(context)
        # Capture before-state at the start of choose_action (before LLM call mutates anything).
        _ms_before = _serialize_state(context.loop_memory.continuity.mission_state)
        _rs_before = _serialize_state(context.loop_memory.continuity.resolution_state)
        _refs_before = dict(context.loop_memory.continuity.latest_refs)

        def _emit_observability(*, parse_ok: bool, parse_reason_code: str | None) -> None:
            emit_prompt_event_observability(
                prompt_event_observer=context.prompt_event_observer,
                model_name=self.model_name,
                context=context,
                pe_id_suffix="kernel_llm",
                surface="orchestration_kernel_llm_turn",
                outcome_kind_parsed="kernel_action_plan_parsed",
                outcome_kind_failed="kernel_action_plan_parse_failed",
                prompt_char_count=prompt_char_count,
                parse_ok=parse_ok,
                parse_reason_code=parse_reason_code,
                prompt_mode=prompt_mode,
                log_label="kernel llm",
            )

        def _audit(
            *,
            parse_ok: bool,
            parse_rc: str | None = None,
            plan: Any = None,
            repair_records: list[dict[str, Any]] | None = None,
        ) -> None:
            observer = context.raw_llm_io_observer
            if observer is None:
                return
            raw_response_text = extract_audit_text(raw_response)
            provider_audit = _provider_audit_fields(raw_response, raw_response_text=raw_response_text)
            record = lifecycle_jsonable(
                {
                    "turn_index": int(context.loop_memory.iterations),
                    "started_at_epoch_seconds": _t0,
                    "finished_at_epoch_seconds": time.time(),
                    "prompt_mode": prompt_mode,
                    "raw_prompt_text": prompt,
                    "raw_llm_response_text": raw_response_text,
                    **provider_audit,
                    "parse_ok": parse_ok,
                    "parse_reason_code": parse_rc,
                    "parsed_action_plan": lifecycle_jsonable(plan) if plan is not None else None,
                    "repair_attempted": bool(repair_records),
                    "repair_records": repair_records or [],
                    # Deprecated scalar fields kept for backward compat with existing consumers.
                    "repair_parse_ok": repair_records[0]["repair_parse_ok"] if repair_records else None,
                    "repair_parse_reason_code": repair_records[0]["repair_parse_reason_code"] if repair_records else None,
                    "mission_state_before": _ms_before,
                    "resolution_state_before": _rs_before,
                    "latest_refs_before": _refs_before,
                    "contract_feedback": dict(context.loop_memory.contract_feedback),
                    "host_hydration_before_turn": build_host_hydration_before_turn(
                        pending_agent_hydration=context.loop_memory.continuity.pending_agent_hydration,
                        pinned_refs_hydration=context.loop_memory.continuity.pinned_refs_hydration,
                    ),
                }
            )
            try:
                observer.observe_llm_io(record)
            except Exception:
                _LOG.warning("raw_llm_io_observer raised; ignoring", exc_info=True)

        if prompt_mode == "resume":
            prompt_builder = build_resume_prompt_document
        elif prompt_mode == "state_repair":
            prompt_builder = build_state_repair_prompt_document
        elif prompt_mode == "turn_recovery":
            prompt_builder = build_turn_recovery_prompt_document
        else:
            prompt_builder = build_choose_action_prompt_document
        prompt_doc = prompt_builder(
            composed_input=self.composed_input,
            opaque_launch_context=self.opaque_launch_context,
            context=context,
            projection=projection,
            journal_verbatim_keep_n=max(0, int(self.continuity_journal_verbatim_keep_n)),
        )
        prompt = prompt_doc.prompt_text
        prompt_char_count = len(prompt)
        # Drain accumulated image evidence from this iteration's tool calls.
        # Clear before the call so a failed or retried call doesn't re-send the same images.
        image_evidence = list(context.loop_memory.pending_image_evidence)
        context.loop_memory.pending_image_evidence.clear()
        call_opts = LlmCallOptions(
            output_mode="json_object",
            image_attachments=tuple(image_evidence),
            phase=prompt_doc.call_phase,
        )
        available_tool_ids = tuple(self.composed_input.tool_handlers.keys())
        parse_exc: ModelActionParseError | None = None
        raw_response: Any = None
        try:
            raw_response = self.text_model_caller(prompt, self.model_name, call_options=call_opts)
            plan = parse_action_plan_response(
                raw_response,
                available_tool_ids=available_tool_ids,
                tool_batch_policies=_tool_batch_policies_for_turn(
                    self.composed_input, self.opaque_launch_context,
                ),
                domain_batch_policy=resolve_domain_action_batch_policy(
                    self.opaque_launch_context,
                ),
            )
        except ModelActionParseError as exc:
            parse_exc = exc
        except Exception as exc:
            classification = classify_model_failure(exception=exc)
            parse_rc = (
                classification.reason_code
                if classification.resumable
                else "model_caller_exception"
            )
            _emit_observability(parse_ok=False, parse_reason_code=parse_rc)
            if classification.resumable:
                _restore_drained_image_evidence(context, image_evidence)
                raise ResumableModelInterruption(
                    classification=classification,
                    iteration=int(context.loop_memory.iterations),
                    prompt_mode=prompt_mode,
                ) from exc
            raise
        if parse_exc is not None:
            if not is_repairable_action_plan_error(parse_exc.reason_code):
                raw_response_text = extract_audit_text(raw_response)
                provider_audit = _provider_audit_fields(raw_response, raw_response_text=raw_response_text)
                classification = classify_model_failure(
                    raw_response=raw_response if isinstance(raw_response, Mapping) else None,
                )
                parse_rc = (
                    classification.reason_code
                    if classification.resumable
                    else parse_exc.reason_code
                )
                _emit_observability(parse_ok=False, parse_reason_code=parse_rc)
                _audit(parse_ok=False, parse_rc=parse_rc, repair_records=None)
                if classification.resumable:
                    _restore_drained_image_evidence(context, image_evidence)
                    raise ResumableModelInterruption(
                        classification=classification,
                        iteration=int(context.loop_memory.iterations),
                        prompt_mode=prompt_mode,
                        extra=provider_audit,
                    ) from parse_exc
                if is_recoverable_output_failure(
                    reason_code=parse_exc.reason_code,
                    raw_response=raw_response,
                    raw_response_text=raw_response_text,
                ):
                    raise RecoverableTurnFailure(
                        {
                            "iteration": int(context.loop_memory.iterations),
                            "prompt_mode": prompt_mode,
                            "reason_code": parse_exc.reason_code,
                            "message": str(parse_exc),
                            "prompt_char_count": prompt_char_count,
                            "active_item_id": context.loop_memory.continuity.active_item_id,
                            "hitl_state": context.loop_memory.hitl.hitl_state,
                            "pending_hitl_integration_prompt_ids": [
                                str(row.get("prompt_id"))
                                for row in context.loop_memory.hitl.answered_hitl_responses
                                if isinstance(row, Mapping) and row.get("prompt_id")
                            ],
                            **provider_audit,
                        }
                    ) from parse_exc
                raise parse_exc
            # One focused repair attempt before hard failure.
            # Reuse the original call_opts.image_attachments so image-grounded turns retain
            # their visual context even when the failure was a formatting-only parse error.
            repair_attempt = attempt_repair(
                model_caller=self.text_model_caller,
                model_name=self.model_name,
                prior_prompt_mode=prompt_mode,
                previous_response_text=extract_audit_text(raw_response),
                original_exc=parse_exc,
                available_tool_ids=available_tool_ids,
                original_image_attachments=call_opts.image_attachments,
                tool_batch_policies=_tool_batch_policies_for_turn(
                    self.composed_input, self.opaque_launch_context,
                ),
                domain_batch_policy=resolve_domain_action_batch_policy(
                    self.opaque_launch_context,
                ),
            )
            _repair_rec = {
                "repair_prompt_mode": "repair",
                "repair_prompt_text": repair_attempt.repair_prompt_text,
                "repair_raw_response_text": repair_attempt.repair_raw_response_text,
                "repair_parse_ok": repair_attempt.repair_parse_ok,
                "repair_parse_reason_code": repair_attempt.repair_parse_reason_code,
                "repair_parsed_action_plan": (
                    jsonable(repair_attempt.repair_parsed_action_plan)
                    if repair_attempt.repair_parsed_action_plan is not None else None
                ),
            }
            if repair_attempt.repair_parse_ok and repair_attempt.repair_parsed_action_plan is not None:
                context.loop_memory.contract_feedback = {
                    "reason_code": parse_exc.reason_code,
                    "message": str(parse_exc),
                    "repair_attempted": True,
                    "repair_outcome": "repaired",
                }
                context.loop_memory.turn_recovery.clear()
                _emit_observability(parse_ok=True, parse_reason_code="repaired")
                _audit(parse_ok=False, parse_rc=parse_exc.reason_code,
                       plan=repair_attempt.repair_parsed_action_plan, repair_records=[_repair_rec])
                return repair_attempt.repair_parsed_action_plan
            # Repair also failed — hard failure with the repair's error.
            repair_error = repair_attempt.repair_error  # always set when repair_parse_ok is False
            assert repair_error is not None
            context.loop_memory.contract_feedback = {
                "reason_code": repair_error.reason_code,
                "message": str(repair_error),
                "repair_attempted": True,
                "repair_outcome": "failed",
            }
            _emit_observability(parse_ok=False, parse_reason_code=repair_error.reason_code)
            _audit(parse_ok=False, parse_rc=parse_exc.reason_code, repair_records=[_repair_rec])
            raise repair_error
        # Clean turn — clear stale contract feedback.
        context.loop_memory.contract_feedback = {}
        context.loop_memory.turn_recovery.clear()
        _emit_observability(parse_ok=True, parse_reason_code=None)
        _audit(parse_ok=True, plan=plan, repair_records=None)
        return plan

    def evaluate_terminal(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
    ):
        del context, projection
        return None


def _tool_batch_policies_for_turn(
    composed_input: ComposedTurnInput,
    opaque_launch_context: Mapping[str, Any],
):
    del opaque_launch_context
    return resolve_tool_batch_policies(composed_input.surface_payloads)


def _serialize_state(state: Any) -> Any:
    """Best-effort serialization of a Pydantic model or plain value for audit records."""
    if state is None:
        return None
    if hasattr(state, "model_dump"):
        try:
            return state.model_dump(mode="json")
        except Exception:
            return str(state)
    return state


def _turn_snapshot(composed_input: ComposedTurnInput) -> dict[str, Any]:
    return {
        "surface_payloads": {
            surface_id: jsonable(payload)
            for surface_id, payload in composed_input.surface_payloads.items()
        },
        "tool_ids": list(composed_input.tool_handlers.keys()),
    }


def _provider_audit_fields(
    raw_response: Any,
    *,
    raw_response_text: str,
) -> dict[str, Any]:
    if not isinstance(raw_response, Mapping):
        return {
            "provider_finish_reason": None,
            "provider_prompt_tokens": None,
            "provider_completion_tokens": None,
            "provider_reasoning_tokens": None,
            "provider_total_tokens": None,
            "provider_error": None,
            "provider_model": None,
            "api_model": None,
            "raw_llm_response_char_count": len(raw_response_text) if raw_response_text else 0,
            "raw_llm_response_tail": raw_response_text[-1000:] if raw_response_text else None,
        }

    usage = raw_response.get("usage")
    prompt_tokens = None
    completion_tokens = None
    reasoning_tokens = None
    total_tokens = None
    if isinstance(usage, Mapping):
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        reasoning_tokens = usage.get("reasoning_tokens")
        total_tokens = usage.get("total_tokens")

    char_count = len(raw_response_text) if raw_response_text else raw_response.get("char_count")
    if not isinstance(char_count, int):
        char_count = 0

    return {
        "provider_finish_reason": raw_response.get("finish_reason"),
        "provider_prompt_tokens": prompt_tokens,
        "provider_completion_tokens": completion_tokens,
        "provider_reasoning_tokens": reasoning_tokens,
        "provider_total_tokens": total_tokens,
        "provider_error": raw_response.get("error"),
        "provider_model": raw_response.get("provider_model") or raw_response.get("model"),
        "api_model": raw_response.get("api_model"),
        "raw_llm_response_char_count": char_count,
        "raw_llm_response_tail": raw_response_text[-1000:] if raw_response_text else None,
    }
