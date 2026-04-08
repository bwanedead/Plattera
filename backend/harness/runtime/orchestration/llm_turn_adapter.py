"""Generic LLM-backed orchestration adapter — thin bridge only.

Wires together the LLM caller, the choose-action prompt builder, the action-plan
parser, and the continuity compaction subsystem. Does not own any of their internals.
"""

from __future__ import annotations

import dataclasses
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
from .action_plan_parser import ModelActionParseError, is_repairable_action_plan_error, parse_action_plan_response
from .contracts import ActionPlan, OrchestrationAdapter, OrchestratorContext, SharedStateProjection
from .llm_prompt_builder import build_choose_action_prompt, jsonable
from .trace_collector import KernelTraceCollector


@dataclass(frozen=True)
class _RepairAttempt:
    """Full I/O record for one repair LLM call."""

    repair_prompt_text: str
    repair_raw_response_text: str
    repair_parse_ok: bool
    repair_parse_reason_code: str | None
    repair_parsed_action_plan: ActionPlan | None
    repair_error: ModelActionParseError | None

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
    _raw_io_cb: Callable[[dict[str, Any]], None] | None = field(default=None, init=False, repr=False, compare=False)
    _turn_result_cb: Callable[[dict[str, Any]], None] | None = field(default=None, init=False, repr=False, compare=False)

    def wire_identity_trace_cb(self, callback: IdentityTraceCallback | None) -> None:
        """Register kernel observability hook (one mechanical ``prompt_event`` per LLM call)."""
        object.__setattr__(self, "_identity_trace_cb", callback)

    def wire_raw_io_cb(self, cb: Callable[[dict[str, Any]], None] | None) -> None:
        """Register per-turn raw LLM I/O audit callback (prompt text + raw response + parse outcome)."""
        object.__setattr__(self, "_raw_io_cb", cb)

    def wire_turn_result_cb(self, cb: Callable[[dict[str, Any]], None] | None) -> None:
        """Register per-turn completion callback (tool request/result, after-state snapshots)."""
        object.__setattr__(self, "_turn_result_cb", cb)

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

    def on_turn_completed(
        self,
        turn_index: int,
        *,
        tool_request: dict[str, Any] | None,
        tool_result_raw: dict[str, Any] | None,
        mission_state_after: Any,
        resolution_state_after: Any,
        latest_refs_after: dict[str, Any],
        state_patch_feedback: dict[str, Any],
        terminal_decision: str | None,
    ) -> None:
        """Discoverable hook called by the orchestrator after each turn completes.

        Supplements the matching per-turn audit record with post-execution data.
        """
        cb = self._turn_result_cb
        if cb is None:
            return
        try:
            cb({
                "turn_index": turn_index,
                "tool_request": tool_request,
                "tool_result_raw": tool_result_raw,
                "mission_state_after": _serialize_state(mission_state_after),
                "resolution_state_after": _serialize_state(resolution_state_after),
                "latest_refs_after": dict(latest_refs_after),
                "state_patch_feedback": dict(state_patch_feedback),
                "terminal_decision": terminal_decision,
            })
        except Exception:
            _LOG.warning("turn_result_cb raised; ignoring", exc_info=True)

    def choose_action(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
    ) -> ActionPlan:
        _t0 = time.time()
        # Capture before-state at the start of choose_action (before LLM call mutates anything).
        _ms_before = _serialize_state(context.loop_memory.continuity.mission_state)
        _rs_before = _serialize_state(context.loop_memory.continuity.resolution_state)
        _refs_before = dict(context.loop_memory.continuity.latest_refs)

        def _audit(*, parse_ok: bool, parse_rc: str | None = None, plan: Any = None,
                   repair_records: list[dict[str, Any]] | None = None) -> None:
            cb = self._raw_io_cb
            if cb is None:
                return
            try:
                cb({"turn_index": int(context.loop_memory.iterations),
                    "started_at_epoch_seconds": _t0, "finished_at_epoch_seconds": time.time(),
                    "raw_prompt_text": prompt, "raw_llm_response_text": _audit_text(raw_response),
                    "parse_ok": parse_ok, "parse_reason_code": parse_rc,
                    "parsed_action_plan": jsonable(plan) if plan is not None else None,
                    "repair_attempted": bool(repair_records),
                    "repair_records": repair_records or [],
                    # Deprecated scalar fields kept for backward compat with existing consumers.
                    "repair_parse_ok": repair_records[0]["repair_parse_ok"] if repair_records else None,
                    "repair_parse_reason_code": repair_records[0]["repair_parse_reason_code"] if repair_records else None,
                    "mission_state_before": _ms_before,
                    "resolution_state_before": _rs_before,
                    "latest_refs_before": _refs_before,
                    "contract_feedback": dict(context.loop_memory.contract_feedback)})
            except Exception:
                _LOG.warning("raw_io_cb raised; ignoring", exc_info=True)

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
        raw_response: Any = None
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
            if not is_repairable_action_plan_error(parse_exc.reason_code):
                # Provider / transport failure — the LLM cannot repair this by reformatting.
                # Emit observability for the original failure and surface it immediately.
                self._emit_kernel_llm_observability(
                    context=context,
                    prompt_char_count=prompt_char_count,
                    parse_ok=False,
                    parse_reason_code=parse_exc.reason_code,
                )
                _audit(parse_ok=False, parse_rc=parse_exc.reason_code, repair_records=None)
                raise parse_exc
            # One focused repair attempt before hard failure.
            # Reuse the original call_opts.image_attachments so image-grounded turns retain
            # their visual context even when the failure was a formatting-only parse error.
            repair_attempt = _attempt_repair(
                model_caller=self.text_model_caller,
                model_name=self.model_name,
                original_prompt=prompt,
                original_exc=parse_exc,
                available_tool_ids=available_tool_ids,
                original_image_attachments=call_opts.image_attachments,
            )
            _repair_rec = {
                "repair_prompt_text": repair_attempt.repair_prompt_text,
                "repair_raw_response_text": repair_attempt.repair_raw_response_text,
                "repair_parse_ok": repair_attempt.repair_parse_ok,
                "repair_parse_reason_code": repair_attempt.repair_parse_reason_code,
                "repair_parsed_action_plan": (
                    dataclasses.asdict(repair_attempt.repair_parsed_action_plan)
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
                self._emit_kernel_llm_observability(
                    context=context,
                    prompt_char_count=prompt_char_count,
                    parse_ok=True,
                    parse_reason_code="repaired",
                )
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
            self._emit_kernel_llm_observability(
                context=context,
                prompt_char_count=prompt_char_count,
                parse_ok=False,
                parse_reason_code=repair_error.reason_code,
            )
            _audit(parse_ok=False, parse_rc=parse_exc.reason_code, repair_records=[_repair_rec])
            raise repair_error
        # Clean turn — clear stale contract feedback.
        context.loop_memory.contract_feedback = {}
        self._emit_kernel_llm_observability(
            context=context,
            prompt_char_count=prompt_char_count,
            parse_ok=True,
            parse_reason_code=None,
        )
        _audit(parse_ok=True, plan=plan, repair_records=None)
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


def _audit_text(raw: Any) -> str:
    """Best-effort extraction of response text from raw model caller output, for audit only."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, Mapping):
        for k in ("text", "content", "output_text", "error"):
            v = raw.get(k)
            if isinstance(v, str):
                return v
    return "" if raw is None else str(raw)


def _attempt_repair(
    *,
    model_caller: TextModelCaller,
    model_name: str,
    original_prompt: str,
    original_exc: ModelActionParseError,
    available_tool_ids: tuple[str, ...],
    original_image_attachments: tuple[dict[str, Any], ...] = (),
) -> _RepairAttempt:
    """Issue one focused repair prompt and attempt to parse the response.

    Carries forward ``original_image_attachments`` so that image-grounded turns
    retain their visual context even when the failure was a formatting-only parse error.

    Returns a ``_RepairAttempt`` with full I/O regardless of outcome.
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
    raw_repair: Any = None
    try:
        raw_repair = model_caller(repair_prompt, model_name, call_options=repair_opts)
        plan = parse_action_plan_response(raw_repair, available_tool_ids=available_tool_ids)
        return _RepairAttempt(
            repair_prompt_text=repair_prompt,
            repair_raw_response_text=_audit_text(raw_repair),
            repair_parse_ok=True,
            repair_parse_reason_code=None,
            repair_parsed_action_plan=plan,
            repair_error=None,
        )
    except ModelActionParseError as exc:
        return _RepairAttempt(
            repair_prompt_text=repair_prompt,
            repair_raw_response_text=_audit_text(raw_repair),
            repair_parse_ok=False,
            repair_parse_reason_code=exc.reason_code,
            repair_parsed_action_plan=None,
            repair_error=exc,
        )
    except Exception:
        err = ModelActionParseError("model_caller_exception", "repair attempt raised unexpected exception")
        return _RepairAttempt(
            repair_prompt_text=repair_prompt,
            repair_raw_response_text=_audit_text(raw_repair),
            repair_parse_ok=False,
            repair_parse_reason_code="model_caller_exception",
            repair_parsed_action_plan=None,
            repair_error=err,
        )


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
