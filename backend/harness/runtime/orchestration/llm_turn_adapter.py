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

from harness.runtime.llm.streaming_config import apply_streaming_to_call_options
from services.llm.call_options import LlmCallOptions

from ..composition import ComposedTurnInput
from ..model_failure_classifier import classify_model_failure
from harness.runtime.llm.instrumented_caller import extract_trace_from_exception
from .action_plan_parser import ModelActionParseError, is_repairable_action_plan_error, parse_action_plan_response
from .contracts import ActionPlan, OrchestrationAdapter, OrchestratorContext, SharedStateProjection
from .llm_prompt_builder import (
    build_choose_action_prompt_document,
    build_resume_prompt_document,
    build_state_repair_prompt_document,
    build_turn_recovery_prompt_document,
    prompt_visible_launch_context,
)
from .llm_turn_choose_action_support import (
    build_llm_io_audit_record,
    build_repair_audit_record,
    provider_audit_fields,
    restore_drained_image_evidence,
    serialize_state,
    tool_batch_policies_for_turn,
    turn_snapshot,
)
from .llm_turn_lifecycle import (
    emit_prompt_event_observability,
    resolve_choose_action_prompt_mode,
)
from .recoverable_turn_failure import RecoverableTurnFailure, is_recoverable_output_failure
from .repair_lane import TextModelCaller, attempt_repair, count_attempted_actions_in_text, extract_audit_text
from .result_delivery_hooks import acknowledge_prompt_result_delivery_contact
from .resumable_model_interruption import ResumableModelInterruption
from .subtasks.registry import build_composed_subtask_registry
from .tool_batch_policy import resolve_domain_action_batch_policy

_LOG = logging.getLogger(__name__)

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
        turn_snapshot_payload = turn_snapshot(self.composed_input)
        ts = time.time()
        prior_ms = context.loop_memory.continuity.mission_state
        prior_rs = context.loop_memory.continuity.resolution_state

        mo = dict(prior_ms.opaque_payload)
        mo["launch_context"] = prompt_visible_launch_context(self.opaque_launch_context)
        mo["turn_snapshot"] = turn_snapshot_payload

        ro = dict(prior_rs.opaque_payload)
        ro["turn_snapshot"] = turn_snapshot_payload

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
        ms_before = serialize_state(context.loop_memory.continuity.mission_state)
        rs_before = serialize_state(context.loop_memory.continuity.resolution_state)
        refs_before = dict(context.loop_memory.continuity.latest_refs)

        prompt_budget_holder: dict[str, Any] | None = None

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
                prompt_budget=prompt_budget_holder,
            )

        def _audit(
            *,
            parse_ok: bool,
            parse_rc: str | None = None,
            plan: Any = None,
            repair_records: list[dict[str, Any]] | None = None,
            parse_error_detail: str | None = None,
            original_action_count_attempted: int | None = None,
            extra_llm_call_traces: list[dict[str, Any]] | None = None,
        ) -> None:
            structured_state = prompt_doc.prompt_body.get("structured_state")
            prompt_observability_summary = None
            if isinstance(structured_state, dict):
                prompt_observability_summary = structured_state.get("prompt_observability_summary")
            context.loop_memory.telemetry.register_turn_contact(
                turn_index=int(context.loop_memory.iterations),
                prompt_char_count=prompt_char_count,
                started_at_epoch_seconds=_t0,
                finished_at_epoch_seconds=time.time(),
                resolution_state_before=rs_before if isinstance(rs_before, dict) else None,
            )
            record = build_llm_io_audit_record(
                context=context,
                started_at_epoch_seconds=_t0,
                prompt_mode=prompt_mode,
                prompt=prompt,
                raw_response=raw_response,
                parse_ok=parse_ok,
                parse_reason_code=parse_rc,
                plan=plan,
                repair_records=repair_records,
                parse_error_detail=parse_error_detail,
                original_action_count_attempted=original_action_count_attempted,
                mission_state_before=ms_before,
                resolution_state_before=rs_before,
                latest_refs_before=refs_before,
                prompt_observability_summary=(
                    prompt_observability_summary
                    if isinstance(prompt_observability_summary, dict)
                    else None
                ),
                extra_llm_call_traces=extra_llm_call_traces,
            )
            observer = context.raw_llm_io_observer
            if observer is None:
                return
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
        prompt_budget_holder = prompt_doc.prompt_budget
        image_evidence = list(context.loop_memory.pending_image_evidence)
        context.loop_memory.pending_image_evidence.clear()
        call_opts = apply_streaming_to_call_options(
            LlmCallOptions(
                output_mode="json_object",
                image_attachments=tuple(image_evidence),
                phase=prompt_doc.call_phase,
            ),
            run_context=context.opaque_run_context,
        )
        available_tool_ids = tuple(self.composed_input.tool_handlers.keys())
        tool_batch_policies = tool_batch_policies_for_turn(
            self.composed_input,
            opaque_run_context=context.opaque_run_context,
        )
        domain_batch_policy = resolve_domain_action_batch_policy(self.opaque_launch_context)
        subtask_registry = build_composed_subtask_registry(
            surface_payloads=self.composed_input.surface_payloads,
            opaque_run_context=context.opaque_run_context,
        )
        parse_exc: ModelActionParseError | None = None
        raw_response: Any = None
        try:
            raw_response = self.text_model_caller(prompt, self.model_name, call_options=call_opts)
        except Exception as exc:
            classification = classify_model_failure(exception=exc)
            parse_rc = (
                classification.reason_code
                if classification.resumable
                else "model_caller_exception"
            )
            _emit_observability(parse_ok=False, parse_reason_code=parse_rc)
            failure_trace = extract_trace_from_exception(exc)
            if failure_trace is not None:
                _audit(
                    parse_ok=False,
                    parse_rc=parse_rc,
                    parse_error_detail=str(exc),
                    extra_llm_call_traces=[failure_trace],
                )
            if classification.resumable:
                restore_drained_image_evidence(context, image_evidence)
                raise ResumableModelInterruption(
                    classification=classification,
                    iteration=int(context.loop_memory.iterations),
                    prompt_mode=prompt_mode,
                ) from exc
            raise
        acknowledge_prompt_result_delivery_contact(
            context.loop_memory.continuity.pending_result_deliveries, metadata=prompt_doc.result_delivery_contact
        )
        try:
            plan = parse_action_plan_response(
                raw_response,
                available_tool_ids=available_tool_ids,
                tool_batch_policies=tool_batch_policies,
                domain_batch_policy=domain_batch_policy,
                subtask_profile_registry=subtask_registry,
            )
        except ModelActionParseError as exc:
            parse_exc = exc
        if parse_exc is not None:
            if not is_repairable_action_plan_error(parse_exc.reason_code):
                raw_response_text = extract_audit_text(raw_response)
                provider_audit = provider_audit_fields(raw_response, raw_response_text=raw_response_text)
                classification = classify_model_failure(
                    raw_response=raw_response if isinstance(raw_response, Mapping) else None,
                )
                parse_rc = (
                    classification.reason_code
                    if classification.resumable
                    else parse_exc.reason_code
                )
                _emit_observability(parse_ok=False, parse_reason_code=parse_rc)
                _prior_text = extract_audit_text(raw_response)
                _audit(
                    parse_ok=False,
                    parse_rc=parse_rc,
                    repair_records=None,
                    parse_error_detail=str(parse_exc),
                    original_action_count_attempted=count_attempted_actions_in_text(_prior_text),
                )
                if classification.resumable:
                    restore_drained_image_evidence(context, image_evidence)
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
            repair_attempt = attempt_repair(
                model_caller=self.text_model_caller,
                model_name=self.model_name,
                prior_prompt_mode=prompt_mode,
                previous_response_text=extract_audit_text(raw_response),
                original_exc=parse_exc,
                available_tool_ids=available_tool_ids,
                original_image_attachments=call_opts.image_attachments,
                tool_batch_policies=tool_batch_policies,
                domain_batch_policy=domain_batch_policy,
                subtask_profile_registry=subtask_registry,
                run_context=context.opaque_run_context,
            )
            repair_rec = build_repair_audit_record(repair_attempt)
            repaired_plan = repair_attempt.repair_parsed_action_plan
            if repair_attempt.repair_parse_ok and repaired_plan is not None:
                context.loop_memory.contract_feedback = {
                    "reason_code": parse_exc.reason_code,
                    "message": str(parse_exc),
                    "repair_attempted": True,
                    "repair_outcome": "repaired",
                }
                context.loop_memory.turn_recovery.clear()
                _emit_observability(parse_ok=True, parse_reason_code="repaired")
                _audit(
                    parse_ok=False,
                    parse_rc=parse_exc.reason_code,
                    plan=repaired_plan,
                    repair_records=[repair_rec],
                    parse_error_detail=str(parse_exc),
                    original_action_count_attempted=count_attempted_actions_in_text(
                        extract_audit_text(raw_response)
                    ),
                )
                return repaired_plan
            repair_error = repair_attempt.repair_error
            assert repair_error is not None
            context.loop_memory.contract_feedback = {
                "reason_code": repair_error.reason_code,
                "message": str(repair_error),
                "repair_attempted": True,
                "repair_outcome": "failed",
            }
            _emit_observability(parse_ok=False, parse_reason_code=repair_error.reason_code)
            _audit(
                parse_ok=False,
                parse_rc=parse_exc.reason_code,
                repair_records=[repair_rec],
                parse_error_detail=str(parse_exc),
                original_action_count_attempted=count_attempted_actions_in_text(
                    extract_audit_text(raw_response)
                ),
            )
            raise repair_error
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
