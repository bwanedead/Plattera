from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from services.llm.call_options import LlmCallOptions

from ..composition import ComposedTurnInput
from ..memory.continuity_compaction import (
    apply_continuity_compaction_result,
    parse_compaction_response,
    prepare_continuity_compaction,
)
from .contracts import OrchestratorContext, SharedStateProjection
from .lifecycle import PreChooseActionParticipant, PromptEventObserver
from .llm_prompt_builder import (
    build_choose_action_prompt_document,
    build_resume_prompt_document,
    build_state_repair_prompt_document,
    build_turn_recovery_prompt_document,
)
from .repair_lane import TextModelCaller, should_use_state_repair_lane
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)


def resolve_choose_action_prompt_mode(context: OrchestratorContext) -> str:
    if context.loop_memory.turn_recovery.has_pending_recovery():
        return "turn_recovery"
    hitl = context.loop_memory.hitl
    if hitl.hitl_state == "answered_unintegrated" or hitl.pending_feedback_response is not None:
        return "resume"
    if should_use_state_repair_lane(context.loop_memory.continuity.state_patch_feedback):
        return "state_repair"
    return "full_choose_action"


def emit_prompt_event_observability(
    *,
    prompt_event_observer: PromptEventObserver | None,
    model_name: str,
    context: OrchestratorContext,
    pe_id_suffix: str,
    surface: str,
    outcome_kind_parsed: str,
    outcome_kind_failed: str,
    prompt_char_count: int,
    parse_ok: bool,
    parse_reason_code: str | None,
    prompt_mode: str,
    log_label: str,
    prompt_budget: Mapping[str, Any] | None = None,
) -> None:
    it = int(context.loop_memory.iterations)
    prompt_event_id = f"{context.request_id_prefix}:iter{it}:{pe_id_suffix}"
    metadata: dict[str, Any] = {
        "prompt_event_id": prompt_event_id,
        "surface": surface,
        "model": model_name,
        "prompt_char_count": prompt_char_count,
        "prompt_mode": prompt_mode,
    }
    if prompt_budget:
        metadata["prompt_budget"] = dict(prompt_budget)
    prompt_event: dict[str, Any] = {
        "metadata": metadata,
        "outcome_kind": outcome_kind_parsed if parse_ok else outcome_kind_failed,
        "outcome_ref": parse_reason_code,
    }
    context.loop_memory.telemetry.register_prompt_event(
        prompt_event_id=prompt_event_id,
        surface=surface,
    )
    context.loop_memory.telemetry.register_llm_contact()
    if prompt_event_observer is None:
        return
    try:
        prompt_event_observer.observe_prompt_event({"prompt_event": prompt_event, "iteration": it})
    except Exception:
        _LOG.warning("%s prompt_event_observer raised; ignoring", log_label, exc_info=True)


@dataclass(frozen=True)
class LlmTurnPreChooseActionParticipant(PreChooseActionParticipant):
    composed_input: ComposedTurnInput
    text_model_caller: TextModelCaller
    model_name: str
    opaque_launch_context: Mapping[str, Any] = field(default_factory=dict)
    continuity_compaction_prompt_char_threshold: int | None = None
    continuity_compaction_trigger_fraction: float | None = None
    continuity_compaction_max_prompt_chars: int | None = None
    continuity_journal_verbatim_keep_n: int = 3
    prompt_event_observer: PromptEventObserver | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def before_choose_action(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
        *,
        tracer: KernelTraceCollector,
    ) -> None:
        """Mechanical context-window compaction: separate LLM call, not a kernel action turn."""
        keep_n = max(0, int(self.continuity_journal_verbatim_keep_n))
        prompt_mode = resolve_choose_action_prompt_mode(context)
        if prompt_mode == "resume":
            prompt_builder = build_resume_prompt_document
        elif prompt_mode == "state_repair":
            prompt_builder = build_state_repair_prompt_document
        elif prompt_mode == "turn_recovery":
            prompt_builder = build_turn_recovery_prompt_document
        else:
            prompt_builder = build_choose_action_prompt_document
        prompt = prompt_builder(
            composed_input=self.composed_input,
            opaque_launch_context=self.opaque_launch_context,
            context=context,
            projection=projection,
            journal_verbatim_keep_n=keep_n,
        ).prompt_text
        prepared = prepare_continuity_compaction(
            cont=context.loop_memory.continuity,
            choose_action_prompt=prompt,
            model_name=self.model_name,
            trigger_fraction=self.continuity_compaction_trigger_fraction,
            char_threshold=self.continuity_compaction_prompt_char_threshold,
            max_compact_chars=self.continuity_compaction_max_prompt_chars,
            keep_n=keep_n,
        )
        if prepared is None:
            return
        compact_chars = len(prepared.compact_prompt)
        try:
            raw_response = self.text_model_caller(
                prepared.compact_prompt,
                self.model_name,
                call_options=LlmCallOptions(
                    output_mode="json_object",
                    phase="continuity_compaction",
                ),
            )
            summary = parse_compaction_response(raw_response)
        except Exception:
            emit_prompt_event_observability(
                prompt_event_observer=self.prompt_event_observer,
                model_name=self.model_name,
                context=context,
                pe_id_suffix="kernel_continuity_compaction",
                surface="orchestration_kernel_continuity_compaction",
                outcome_kind_parsed="kernel_continuity_compaction_parsed",
                outcome_kind_failed="kernel_continuity_compaction_parse_failed",
                prompt_char_count=compact_chars,
                parse_ok=False,
                parse_reason_code="compaction_parse_failed",
                prompt_mode="compaction",
                log_label="compaction kernel llm",
            )
            _LOG.warning("continuity compaction LLM call failed; skipping compaction update", exc_info=True)
            return
        cont = context.loop_memory.continuity
        apply_continuity_compaction_result(cont, prepared, summary)
        emit_prompt_event_observability(
            prompt_event_observer=self.prompt_event_observer,
            model_name=self.model_name,
            context=context,
            pe_id_suffix="kernel_continuity_compaction",
            surface="orchestration_kernel_continuity_compaction",
            outcome_kind_parsed="kernel_continuity_compaction_parsed",
            outcome_kind_failed="kernel_continuity_compaction_parse_failed",
            prompt_char_count=compact_chars,
            parse_ok=True,
            parse_reason_code=None,
            prompt_mode="compaction",
            log_label="compaction kernel llm",
        )
        tracer.emit_continuity_compacted(
            iteration=int(context.loop_memory.iterations),
            prompt_char_count_estimate_before=prepared.est_chars,
            journal_entries_compacted_count=len(prepared.j_send),
            kernel_step_records_compacted_count=len(prepared.s_send),
            kernel_step_result_records_compacted_count=len(prepared.r_send),
            verbatim_keep_n=keep_n,
            threshold_chars=prepared.trace_threshold,
            compaction_prompt_char_count=compact_chars,
            kernel_compaction_covered_through_turn_index_after=int(
                cont.kernel_compaction_covered_through_turn_index
            ),
            compaction_trigger_mode=prepared.trigger_mode,
            estimated_prompt_tokens=prepared.est_tokens,
            context_window_tokens=prepared.cw_tokens,
            used_context_window_fallback=prepared.used_fb,
            compaction_trigger_fraction=prepared.trigger_fraction,
            estimated_occupancy_fraction=prepared.occ_frac,
        )
