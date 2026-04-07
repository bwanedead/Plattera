"""Generic LLM-backed orchestration adapter — thin bridge only.

Wires together the LLM caller, the choose-action prompt builder, the action-plan
parser, and the continuity compaction subsystem. Does not own any of their internals.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

_LOG = logging.getLogger(__name__)

from services.llm.call_options import LlmCallOptions

from ..composition import ComposedTurnInput
from ..memory.continuity_compaction import (
    PreparedContinuityCompaction as _PreparedContinuityCompaction,
    apply_continuity_compaction_result,
    parse_compaction_response,
    prepare_continuity_compaction,
)
from .action_plan_parser import ModelActionParseError, parse_action_plan_response
from .contracts import ActionPlan, OrchestrationAdapter, OrchestratorContext, SharedStateProjection
from .llm_prompt_builder import build_choose_action_prompt, jsonable
from .trace_collector import KernelTraceCollector

TextModelCaller = Callable[..., Mapping[str, Any] | str]
IdentityTraceCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class LlmTurnOrchestrationAdapter(OrchestrationAdapter):
    composed_input: ComposedTurnInput
    text_model_caller: TextModelCaller
    model_name: str
    opaque_launch_context: Mapping[str, Any] = field(default_factory=dict)
    # When set, ``run_continuity_pre_choose_action`` may run a separate compaction LLM call.
    # Legacy trigger: raw prompt character count (secondary / deprecated vs occupancy fraction).
    continuity_compaction_prompt_char_threshold: int | None = None
    # Preferred trigger: estimated prompt tokens / model context_window >= this fraction.
    continuity_compaction_trigger_fraction: float | None = None
    # Hard cap on compaction LLM prompt size (defaults depend on trigger mode).
    continuity_compaction_max_prompt_chars: int | None = None
    continuity_journal_verbatim_keep_n: int = 5
    _identity_trace_cb: IdentityTraceCallback | None = field(default=None, init=False, repr=False, compare=False)

    def wire_identity_trace_cb(self, callback: IdentityTraceCallback | None) -> None:
        """Register kernel observability hook (one mechanical ``prompt_event`` per LLM call)."""
        object.__setattr__(self, "_identity_trace_cb", callback)

    def run_continuity_pre_choose_action(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
        *,
        tracer: KernelTraceCollector,
    ) -> None:
        """Mechanical context-window compaction: separate LLM call; does not consume a kernel action turn."""
        keep_n = max(0, int(self.continuity_journal_verbatim_keep_n))
        prompt = build_choose_action_prompt(
            composed_input=self.composed_input,
            opaque_launch_context=self.opaque_launch_context,
            context=context,
            projection=projection,
            journal_verbatim_keep_n=keep_n,
        )
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
            raw_response = self.text_model_caller(prepared.compact_prompt, self.model_name)
            summary = parse_compaction_response(raw_response)
        except Exception:
            self._emit_compaction_kernel_llm_observability(
                context=context,
                prompt_char_count=compact_chars,
                parse_ok=False,
                parse_reason_code="compaction_parse_failed",
            )
            _LOG.warning("continuity compaction LLM call failed; skipping compaction update", exc_info=True)
            return
        cont = context.loop_memory.continuity
        apply_continuity_compaction_result(cont, prepared, summary)
        self._emit_compaction_kernel_llm_observability(
            context=context,
            prompt_char_count=compact_chars,
            parse_ok=True,
            parse_reason_code=None,
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

    def initialize(self, context: OrchestratorContext) -> None:
        del context

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        turn_snapshot = _turn_snapshot(self.composed_input)
        ts = time.time()
        prior_ms = context.loop_memory.continuity.mission_state
        prior_rs = context.loop_memory.continuity.resolution_state

        mo = dict(prior_ms.opaque_payload)
        mo["launch_context"] = jsonable(self.opaque_launch_context)
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
        prompt = build_choose_action_prompt(
            composed_input=self.composed_input,
            opaque_launch_context=self.opaque_launch_context,
            context=context,
            projection=projection,
            journal_verbatim_keep_n=max(0, int(self.continuity_journal_verbatim_keep_n)),
        )
        prompt_char_count = len(prompt)
        # Drain accumulated image evidence from this iteration's tool calls.
        # Clear before the call so a failed or retried call doesn't re-send the same images.
        image_evidence = list(context.loop_memory.pending_image_evidence)
        context.loop_memory.pending_image_evidence.clear()
        call_opts = LlmCallOptions(
            output_mode="json_object",
            image_attachments=tuple(image_evidence),
            phase="choose_action",
        )
        available_tool_ids = tuple(self.composed_input.tool_handlers.keys())
        parse_exc: ModelActionParseError | None = None
        try:
            raw_response = self.text_model_caller(prompt, self.model_name, call_options=call_opts)
            plan = parse_action_plan_response(raw_response, available_tool_ids=available_tool_ids)
        except ModelActionParseError as exc:
            parse_exc = exc
        except Exception:
            self._emit_kernel_llm_observability(
                context=context,
                prompt_char_count=prompt_char_count,
                parse_ok=False,
                parse_reason_code="model_caller_exception",
            )
            raise
        if parse_exc is not None:
            # One focused repair attempt before hard failure.
            # Reuse the original call_opts.image_attachments so image-grounded turns retain
            # their visual context even when the failure was a formatting-only parse error.
            repair_result = _attempt_repair(
                model_caller=self.text_model_caller,
                model_name=self.model_name,
                original_prompt=prompt,
                original_exc=parse_exc,
                available_tool_ids=available_tool_ids,
                original_image_attachments=call_opts.image_attachments,
            )
            if isinstance(repair_result, ActionPlan):
                context.loop_memory.contract_feedback = {
                    "reason_code": parse_exc.reason_code,
                    "message": str(parse_exc),
                    "repair_attempted": True,
                    "repair_outcome": "repaired",
                }
                self._emit_kernel_llm_observability(
                    context=context,
                    prompt_char_count=prompt_char_count,
                    parse_ok=True,
                    parse_reason_code="repaired",
                )
                return repair_result
            # Repair also failed — hard failure with the repair's error.
            context.loop_memory.contract_feedback = {
                "reason_code": repair_result.reason_code,
                "message": str(repair_result),
                "repair_attempted": True,
                "repair_outcome": "failed",
            }
            self._emit_kernel_llm_observability(
                context=context,
                prompt_char_count=prompt_char_count,
                parse_ok=False,
                parse_reason_code=repair_result.reason_code,
            )
            raise repair_result
        # Clean turn — clear stale contract feedback.
        context.loop_memory.contract_feedback = {}
        self._emit_kernel_llm_observability(
            context=context,
            prompt_char_count=prompt_char_count,
            parse_ok=True,
            parse_reason_code=None,
        )
        return plan  # type: ignore[return-value]  # assigned in the try block

    def evaluate_terminal(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
    ):
        del context, projection
        return None

    # ------------------------------------------------------------------
    # Observability helpers
    # ------------------------------------------------------------------

    def _emit_identity_prompt_event(
        self,
        context: OrchestratorContext,
        *,
        pe_id_suffix: str,
        surface: str,
        outcome_kind_parsed: str,
        outcome_kind_failed: str,
        prompt_char_count: int,
        parse_ok: bool,
        parse_reason_code: str | None,
        log_label: str,
    ) -> None:
        cb = self._identity_trace_cb
        if cb is None:
            return
        it = int(context.loop_memory.iterations)
        pe_id = f"{context.request_id_prefix}:iter{it}:{pe_id_suffix}"
        prompt_event: dict[str, Any] = {
            "metadata": {
                "prompt_event_id": pe_id,
                "surface": surface,
                "model": self.model_name,
                "prompt_char_count": prompt_char_count,
            },
            "outcome_kind": outcome_kind_parsed if parse_ok else outcome_kind_failed,
            "outcome_ref": parse_reason_code,
        }
        try:
            cb({"prompt_event": prompt_event, "iteration": it})
        except Exception:
            _LOG.warning("%s identity_trace_cb raised; ignoring", log_label, exc_info=True)

    def _emit_kernel_llm_observability(
        self,
        context: OrchestratorContext,
        *,
        prompt_char_count: int,
        parse_ok: bool,
        parse_reason_code: str | None,
    ) -> None:
        self._emit_identity_prompt_event(
            context,
            pe_id_suffix="kernel_llm",
            surface="orchestration_kernel_llm_turn",
            outcome_kind_parsed="kernel_action_plan_parsed",
            outcome_kind_failed="kernel_action_plan_parse_failed",
            prompt_char_count=prompt_char_count,
            parse_ok=parse_ok,
            parse_reason_code=parse_reason_code,
            log_label="kernel llm",
        )

    def _emit_compaction_kernel_llm_observability(
        self,
        context: OrchestratorContext,
        *,
        prompt_char_count: int,
        parse_ok: bool,
        parse_reason_code: str | None,
    ) -> None:
        self._emit_identity_prompt_event(
            context,
            pe_id_suffix="kernel_continuity_compaction",
            surface="orchestration_kernel_continuity_compaction",
            outcome_kind_parsed="kernel_continuity_compaction_parsed",
            outcome_kind_failed="kernel_continuity_compaction_parse_failed",
            prompt_char_count=prompt_char_count,
            parse_ok=parse_ok,
            parse_reason_code=parse_reason_code,
            log_label="compaction kernel llm",
        )


def _attempt_repair(
    *,
    model_caller: TextModelCaller,
    model_name: str,
    original_prompt: str,
    original_exc: ModelActionParseError,
    available_tool_ids: tuple[str, ...],
    original_image_attachments: tuple[dict[str, Any], ...] = (),
) -> ActionPlan | ModelActionParseError:
    """Issue one focused repair prompt and attempt to parse the response.

    Carries forward ``original_image_attachments`` so that image-grounded turns
    retain their visual context even when the failure was a formatting-only parse error.

    Returns the repaired ActionPlan on success, or a ModelActionParseError on failure.
    """
    repair_prompt = (
        original_prompt
        + f"\n\n---\nPrevious response failed action-plan parsing.\n"
        f"reason_code: {original_exc.reason_code}\n"
        f"detail: {original_exc}\n\n"
        "Return exactly one corrected JSON object preserving your intended action semantics. "
        "No markdown. No commentary. One JSON object only."
    )
    repair_opts = LlmCallOptions(
        output_mode="json_object",
        image_attachments=original_image_attachments,
        phase="choose_action_repair",
    )
    try:
        raw = model_caller(repair_prompt, model_name, call_options=repair_opts)
        return parse_action_plan_response(raw, available_tool_ids=available_tool_ids)
    except ModelActionParseError as exc:
        return exc
    except Exception:
        return ModelActionParseError(
            "model_caller_exception",
            "repair attempt raised unexpected exception",
        )


def _turn_snapshot(composed_input: ComposedTurnInput) -> dict[str, Any]:
    return {
        "surface_payloads": {
            surface_id: jsonable(payload)
            for surface_id, payload in composed_input.surface_payloads.items()
        },
        "tool_ids": list(composed_input.tool_handlers.keys()),
    }
