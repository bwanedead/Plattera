"""Generic LLM-backed orchestration adapter for composed turn surfaces.

This module stays blind to domain semantics. It packages opaque turn-surface
data into a generic prompt envelope, asks a text model for one JSON action
plan, and validates that the result is mechanically coherent.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

_LOG = logging.getLogger(__name__)

from ..composition import ComposedTurnInput
from ..memory.continuity_journal import (
    clamp_compacted_summary_text,
    clamp_compaction_prior_for_prompt,
    fold_rows_not_yet_sent_to_compaction,
    kernel_turn_index_of,
    max_kernel_turn_in_rows,
    partition_continuity_for_compaction,
    recent_journal_entries_for_prompt,
    recent_step_records_for_prompt,
    recent_step_result_records_for_prompt,
)
from ..memory.openai_model_limits import (
    estimate_prompt_tokens_from_chars,
    resolve_context_window_tokens,
)
from .contracts import ActionPlan, OrchestrationAdapter, OrchestratorContext, SharedStateProjection
from .trace_collector import KernelTraceCollector


def _compaction_target_summary_char_budget(max_prompt_chars: int) -> int:
    """Mechanical output-size hint for compaction LLM (ties to compaction prompt budget)."""
    return min(12_000, max(800, int(max_prompt_chars) // 6))


TextModelCaller = Callable[..., Mapping[str, Any] | str]

_ALLOWED_ACTION_PLAN_KEYS = {
    "action_type",
    "action_inputs",
    "idempotency_key",
    "skip_execution",
    "wait_for_human",
    "complete_run",
    "rationale",
    "state_patch",
    "continuity_journal_entry",
    "operator_progress_message",
}


class ModelActionParseError(ValueError):
    """Raised when the model output cannot be mechanically parsed into an action plan."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


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
    # Preferred trigger: estimated prompt tokens / model context_window >= this fraction (see openai_model_limits).
    continuity_compaction_trigger_fraction: float | None = None
    # Hard cap on compaction LLM prompt size (defaults depend on trigger mode).
    continuity_compaction_max_prompt_chars: int | None = None
    continuity_journal_verbatim_keep_n: int = 5
    _identity_trace_cb: IdentityTraceCallback | None = field(default=None, init=False, repr=False, compare=False)

    def wire_identity_trace_cb(self, callback: IdentityTraceCallback | None) -> None:
        """Register kernel observability hook (one mechanical ``prompt_event`` per ``choose_action`` LLM call)."""
        object.__setattr__(self, "_identity_trace_cb", callback)

    def run_continuity_pre_choose_action(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
        *,
        tracer: KernelTraceCollector,
    ) -> None:
        """Mechanical context-window compaction: separate LLM call; does not consume a kernel action turn."""
        fraction = self.continuity_compaction_trigger_fraction
        threshold = self.continuity_compaction_prompt_char_threshold
        use_fraction = fraction is not None and float(fraction) > 0
        use_legacy = not use_fraction and threshold is not None and int(threshold) > 0
        if not use_fraction and not use_legacy:
            return
        keep_n = max(0, int(self.continuity_journal_verbatim_keep_n))
        cont = context.loop_memory.continuity
        prompt = _build_prompt(
            composed_input=self.composed_input,
            opaque_launch_context=self.opaque_launch_context,
            context=context,
            projection=projection,
            journal_verbatim_keep_n=keep_n,
        )
        est_chars = len(prompt)
        trace_threshold: int | None
        trigger_mode: str
        est_tokens: int | None = None
        cw_tokens: int | None = None
        used_fb: bool | None = None
        occ_frac: float | None = None
        if use_fraction:
            # Main prompt only includes the verbatim tail; full continuity still occupies context budget.
            carriage_blob = json.dumps(
                {
                    "compacted_continuity_summary": cont.compacted_continuity_summary,
                    "continuity_journal_entries": cont.continuity_journal_entries,
                    "kernel_step_records": cont.kernel_step_records,
                    "kernel_step_result_records": cont.kernel_step_result_records,
                },
                ensure_ascii=False,
                default=str,
            )
            est_chars = max(est_chars, len(carriage_blob))
            cw_tokens, used_fb = resolve_context_window_tokens(self.model_name)
            est_tokens = estimate_prompt_tokens_from_chars(est_chars)
            occ_frac = float(est_tokens) / float(cw_tokens)
            if occ_frac < float(fraction):
                return
            max_compact = self.continuity_compaction_max_prompt_chars
            if max_compact is None or max_compact <= 0:
                max_compact = max(48_000, min(200_000, int(cw_tokens) * 2))
            trace_threshold = None
            trigger_mode = "occupancy_fraction"
        else:
            assert threshold is not None
            if est_chars < int(threshold):
                return
            max_compact = self.continuity_compaction_max_prompt_chars
            if max_compact is None or max_compact <= 0:
                max_compact = max(int(threshold) * 2, 48_000)
            trace_threshold = int(threshold)
            trigger_mode = "legacy_char_threshold"
        target_summary_chars = _compaction_target_summary_char_budget(int(max_compact))
        j_fold, s_fold, r_fold = partition_continuity_for_compaction(
            cont.continuity_journal_entries,
            cont.kernel_step_records,
            cont.kernel_step_result_records,
            keep_n=keep_n,
        )
        j_fold, s_fold, r_fold = fold_rows_not_yet_sent_to_compaction(
            j_fold,
            s_fold,
            r_fold,
            covered_through_turn_index=cont.kernel_compaction_covered_through_turn_index,
        )
        if not j_fold and not s_fold and not r_fold:
            return
        fit = _fit_compaction_prompt_parts(
            cont.compacted_continuity_summary,
            j_fold,
            s_fold,
            r_fold,
            max_chars=int(max_compact),
            target_compacted_summary_chars=target_summary_chars,
        )
        if fit is None:
            return
        prior_out, j_send, s_send, r_send = fit
        if not j_send and not s_send and not r_send:
            return
        compact_prompt = _build_compaction_prompt(
            prior_compacted_continuity_summary=prior_out,
            journal_entries_to_fold=j_send,
            kernel_step_records_to_fold=s_send,
            kernel_step_result_records_to_fold=r_send,
            target_compacted_summary_chars=target_summary_chars,
        )
        compact_chars = len(compact_prompt)
        try:
            raw_response = self.text_model_caller(compact_prompt, self.model_name)
            summary = _coerce_compaction_summary(raw_response)
        except (ModelActionParseError, Exception):
            self._emit_compaction_kernel_llm_observability(
                context=context,
                prompt_char_count=compact_chars,
                parse_ok=False,
                parse_reason_code="compaction_parse_failed",
            )
            _LOG.warning("continuity compaction LLM call failed; skipping compaction update", exc_info=True)
            return
        cont.compacted_continuity_summary = summary
        mx = max_kernel_turn_in_rows(j_send, s_send, r_send)
        if mx is not None:
            cont.kernel_compaction_covered_through_turn_index = max(
                int(cont.kernel_compaction_covered_through_turn_index),
                int(mx),
            )
        self._emit_compaction_kernel_llm_observability(
            context=context,
            prompt_char_count=compact_chars,
            parse_ok=True,
            parse_reason_code=None,
        )
        tracer.emit_continuity_compacted(
            iteration=int(context.loop_memory.iterations),
            prompt_char_count_estimate_before=est_chars,
            journal_entries_compacted_count=len(j_send),
            kernel_step_records_compacted_count=len(s_send),
            kernel_step_result_records_compacted_count=len(r_send),
            verbatim_keep_n=keep_n,
            threshold_chars=trace_threshold,
            compaction_prompt_char_count=compact_chars,
            kernel_compaction_covered_through_turn_index_after=int(cont.kernel_compaction_covered_through_turn_index),
            compaction_trigger_mode=trigger_mode,
            estimated_prompt_tokens=est_tokens,
            context_window_tokens=cw_tokens,
            used_context_window_fallback=used_fb,
            compaction_trigger_fraction=float(fraction) if use_fraction else None,
            estimated_occupancy_fraction=occ_frac,
        )

    def initialize(self, context: OrchestratorContext) -> None:
        del context

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        turn_snapshot = _turn_snapshot(self.composed_input)
        ts = time.time()
        prior_ms = context.loop_memory.continuity.mission_state
        prior_rs = context.loop_memory.continuity.resolution_state

        mo = dict(prior_ms.opaque_payload)
        mo["launch_context"] = _jsonable(self.opaque_launch_context)
        mo["turn_snapshot"] = turn_snapshot

        ro = dict(prior_rs.opaque_payload)
        ro["turn_snapshot"] = turn_snapshot

        resolution_state = prior_rs.model_copy(
            update={
                "opaque_payload": ro,
                "updated_at_epoch_seconds": ts,
            }
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
        prompt = _build_prompt(
            composed_input=self.composed_input,
            opaque_launch_context=self.opaque_launch_context,
            context=context,
            projection=projection,
            journal_verbatim_keep_n=max(0, int(self.continuity_journal_verbatim_keep_n)),
        )
        prompt_char_count = len(prompt)
        try:
            raw_response = self.text_model_caller(prompt, self.model_name)
            plan = _coerce_action_plan(
                raw_response,
                available_tool_ids=tuple(self.composed_input.tool_handlers.keys()),
            )
        except ModelActionParseError as exc:
            self._emit_kernel_llm_observability(
                context=context,
                prompt_char_count=prompt_char_count,
                parse_ok=False,
                parse_reason_code=exc.reason_code,
            )
            raise
        except Exception:
            self._emit_kernel_llm_observability(
                context=context,
                prompt_char_count=prompt_char_count,
                parse_ok=False,
                parse_reason_code="model_caller_exception",
            )
            raise

        self._emit_kernel_llm_observability(
            context=context,
            prompt_char_count=prompt_char_count,
            parse_ok=True,
            parse_reason_code=None,
        )
        return plan

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
        """Mechanical prompt-contact record for kernel LLM surfaces (choose_action / compaction)."""
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

    def evaluate_terminal(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
    ):
        del context, projection
        return None


def _build_prompt(
    *,
    composed_input: ComposedTurnInput,
    opaque_launch_context: Mapping[str, Any],
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
    journal_verbatim_keep_n: int,
) -> str:
    cont = context.loop_memory.continuity
    envelope = {
        "iteration": context.loop_memory.iterations,
        "session_id": context.session_id,
        "request_id_prefix": context.request_id_prefix,
        "launch_context": _jsonable(opaque_launch_context),
        "turn_input": _turn_input_document(composed_input),
        "latest_refs": dict(cont.latest_refs),
        "active_item_id": cont.active_item_id,
        "state_patch_feedback": dict(cont.state_patch_feedback),
        "operator_progress_message": cont.operator_progress_message,
        "compacted_continuity_summary": cont.compacted_continuity_summary,
        "recent_continuity_journal_entries": recent_journal_entries_for_prompt(
            cont.continuity_journal_entries,
            cont.kernel_step_records,
            cont.kernel_step_result_records,
            keep_n=journal_verbatim_keep_n,
        ),
        "recent_kernel_step_records": recent_step_records_for_prompt(
            cont.continuity_journal_entries,
            cont.kernel_step_records,
            cont.kernel_step_result_records,
            keep_n=journal_verbatim_keep_n,
        ),
        "recent_kernel_step_result_records": recent_step_result_records_for_prompt(
            cont.continuity_journal_entries,
            cont.kernel_step_records,
            cont.kernel_step_result_records,
            keep_n=journal_verbatim_keep_n,
        ),
        "projection": _projection_document(projection),
    }
    instruction = (
        "Return exactly one JSON object matching this schema:\n"
        "{"
        '"action_type": string|null, '
        '"action_inputs": object, '
        '"idempotency_key": string, '
        '"skip_execution": boolean, '
        '"wait_for_human": boolean, '
        '"complete_run": boolean, '
        '"rationale": string|null, '
        '"state_patch": object|null, '
        '"continuity_journal_entry": object, '
        '"operator_progress_message": string|null'
        "}\n"
        "continuity_journal_entry: required non-empty JSON object each turn (append-only continuity: observations, decisions, "
        "open threads, expected next). operator_progress_message: optional short user-facing status line; null keeps the prior "
        "message.\n"
        "Envelope fields compacted_continuity_summary, recent_continuity_journal_entries, recent_kernel_step_records, "
        "and recent_kernel_step_result_records are host-labeled memory: the three recent_* lists cover the same last N "
        "distinct kernel turns (journal author payloads, mechanical step rows, and bounded mechanical tool-result rows); "
        "author replacements only via continuity_journal_entry / compaction, not by editing those envelope keys.\n"
        "Optional state_patch: generic { resolution?: { active_item_id, items, relations, opaque_payload }, "
        "mission?: { objective, active_mode, blocker_summary, verification_summary, waiting_summary, "
        "continuity_summary, mission_mode_summary, high_signal_artifact_refs, opaque_payload } — only those keys; "
        "do not put latest_refs_summary, terminal_summary, or prompt_observability_summary in mission (host-owned). "
        "you author all work semantics inside allowed shapes; the runtime merges mechanically "
        "(resolution items merge by item_id: only fields you include are overwritten). "
        "state_patch_feedback in the envelope reports the kernel outcome of the prior patch (applied / rejected / not_applied / no_patch); "
        "when outcome is applied but some resolution item/relation rows were dropped, look for skipped_resolution_rows and row_skips counts.\n"
        "Choose action_type only from the provided tool_ids unless complete_run or wait_for_human is true.\n"
        "Do not wrap the JSON in markdown and do not add commentary."
    )
    return instruction + "\n\n" + json.dumps(envelope, ensure_ascii=False, sort_keys=True)


def _fit_compaction_prompt_parts(
    prior_full: str | None,
    j_fold: list[dict[str, Any]],
    s_fold: list[dict[str, Any]],
    r_fold: list[dict[str, Any]],
    max_chars: int,
    *,
    target_compacted_summary_chars: int,
) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Mechanically fit compaction prompt under ``max_chars``: drop newest fold turns first, then shorten prior."""
    prior = clamp_compaction_prior_for_prompt(prior_full) if prior_full else None
    j_src, s_src, r_src = list(j_fold), list(s_fold), list(r_fold)
    turns = sorted(
        {
            t
            for row in j_src + s_src + r_src
            for t in [kernel_turn_index_of(row)]
            if t is not None
        }
    )
    active: set[int] = set(turns)
    while True:
        j = [e for e in j_src if kernel_turn_index_of(e) in active]
        s = [r for r in s_src if kernel_turn_index_of(r) in active]
        rr = [x for x in r_src if kernel_turn_index_of(x) in active]
        plen = len(
            _build_compaction_prompt(
                prior_compacted_continuity_summary=prior,
                journal_entries_to_fold=j,
                kernel_step_records_to_fold=s,
                kernel_step_result_records_to_fold=rr,
                target_compacted_summary_chars=target_compacted_summary_chars,
            )
        )
        if plen <= max_chars:
            return prior, j, s, rr
        if active:
            active.remove(max(active))
            continue
        if prior:
            if len(prior) <= 500:
                prior = None
            else:
                prior = prior[: max(len(prior) - 4000, 0)].strip() or None
            continue
        _LOG.warning("compaction prompt cannot fit under max_chars=%s; skipping", max_chars)
        return None


def _build_compaction_prompt(
    *,
    prior_compacted_continuity_summary: str | None,
    journal_entries_to_fold: list[dict[str, Any]],
    kernel_step_records_to_fold: list[dict[str, Any]],
    kernel_step_result_records_to_fold: list[dict[str, Any]],
    target_compacted_summary_chars: int,
) -> str:
    envelope = {
        "prior_compacted_continuity_summary": prior_compacted_continuity_summary,
        "journal_entries_to_fold": journal_entries_to_fold,
        "kernel_step_records_to_fold": kernel_step_records_to_fold,
        "kernel_step_result_records_to_fold": kernel_step_result_records_to_fold,
        "target_compacted_summary_chars": int(target_compacted_summary_chars),
    }
    instruction = (
        "Return exactly one JSON object matching this schema:\n"
        '{"compacted_continuity_summary": string}\n'
        "Fold journal_entries_to_fold, kernel_step_records_to_fold, and kernel_step_result_records_to_fold into a single "
        "replacement string for compacted_continuity_summary. If prior_compacted_continuity_summary is non-empty, merge "
        "coherently. target_compacted_summary_chars is a mechanical budget: aim for that many characters in "
        "compacted_continuity_summary (roughly ±25% is acceptable). Stay within the supplied facts; do not wrap in markdown.\n"
    )
    return instruction + "\n\n" + json.dumps(envelope, ensure_ascii=False, sort_keys=True)


def _coerce_compaction_summary(raw_response: Mapping[str, Any] | str) -> str:
    text = _extract_text(raw_response)
    try:
        payload = json.loads(text)
    except Exception as exc:
        raise ModelActionParseError("invalid_compaction_json", "compaction output was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ModelActionParseError("invalid_compaction_json", "compaction output must be a JSON object")
    extra = set(payload.keys()) - {"compacted_continuity_summary"}
    if extra:
        raise ModelActionParseError(
            "invalid_compaction_json",
            f"unexpected compaction keys: {', '.join(sorted(extra))}",
        )
    raw_summary = payload.get("compacted_continuity_summary")
    if not isinstance(raw_summary, str):
        raise ModelActionParseError("invalid_compaction_json", "compacted_continuity_summary must be a string")
    out = clamp_compacted_summary_text(raw_summary)
    if out is None:
        raise ModelActionParseError("invalid_compaction_json", "compacted_continuity_summary was empty")
    return out


def _coerce_action_plan(raw_response: Mapping[str, Any] | str, *, available_tool_ids: tuple[str, ...]) -> ActionPlan:
    text = _extract_text(raw_response)
    try:
        payload = json.loads(text)
    except Exception as exc:
        raise ModelActionParseError("invalid_model_action_json", "model output was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ModelActionParseError("invalid_model_action_json", "model output must be a JSON object")

    unknown_keys = sorted(set(payload.keys()) - _ALLOWED_ACTION_PLAN_KEYS)
    if unknown_keys:
        raise ModelActionParseError(
            "invalid_model_action_json",
            f"unexpected action plan keys: {', '.join(unknown_keys)}",
        )

    action_type = _optional_text(payload.get("action_type"))
    action_inputs = payload.get("action_inputs")
    if action_inputs is None:
        action_inputs = {}
    if not isinstance(action_inputs, Mapping):
        raise ModelActionParseError("invalid_model_action_json", "action_inputs must be an object")

    complete_run = _require_json_bool(payload, "complete_run")
    wait_for_human = _require_json_bool(payload, "wait_for_human")
    skip_execution = _require_json_bool(payload, "skip_execution")

    if complete_run and wait_for_human:
        raise ModelActionParseError("invalid_model_action_json", "complete_run and wait_for_human are mutually exclusive")

    if not complete_run and not wait_for_human:
        if not action_type:
            raise ModelActionParseError("invalid_model_action_json", "action_type is required unless completing or waiting")
        if available_tool_ids and action_type not in available_tool_ids:
            raise ModelActionParseError("invalid_model_action_json", f"unknown action_type: {action_type}")

    state_patch_raw = payload.get("state_patch")
    if state_patch_raw is None:
        state_patch_out: dict[str, Any] | None = None
    elif isinstance(state_patch_raw, dict):
        state_patch_out = dict(state_patch_raw)
    else:
        raise ModelActionParseError(
            "invalid_model_action_json",
            "state_patch must be a JSON object or null",
        )

    cje_raw = payload.get("continuity_journal_entry")
    if cje_raw is None:
        raise ModelActionParseError(
            "invalid_model_action_json",
            "continuity_journal_entry is required and must be a non-empty JSON object",
        )
    if not isinstance(cje_raw, dict):
        raise ModelActionParseError(
            "invalid_model_action_json",
            "continuity_journal_entry must be a JSON object",
        )
    cje_out = dict(cje_raw)
    if len(cje_out) < 1:
        raise ModelActionParseError(
            "invalid_model_action_json",
            "continuity_journal_entry must be a non-empty JSON object",
        )

    opm_raw = payload.get("operator_progress_message")
    if opm_raw is None:
        opm_out: str | None = None
    elif isinstance(opm_raw, str):
        opm_out = _optional_text(opm_raw)
    else:
        raise ModelActionParseError(
            "invalid_model_action_json",
            "operator_progress_message must be a string or null",
        )

    return ActionPlan(
        action_type=action_type or None,
        action_inputs=dict(action_inputs),
        idempotency_key=_optional_text(payload.get("idempotency_key")) or "",
        skip_execution=skip_execution,
        wait_for_human=wait_for_human,
        complete_run=complete_run,
        rationale=_optional_text(payload.get("rationale")),
        state_patch=state_patch_out,
        continuity_journal_entry=cje_out,
        operator_progress_message=opm_out,
    )


def _extract_text(raw_response: Mapping[str, Any] | str) -> str:
    if isinstance(raw_response, str):
        text = raw_response.strip()
        if not text:
            raise ModelActionParseError("invalid_model_action_json", "model output was empty")
        return text
    if raw_response.get("success") is False:
        raise ModelActionParseError(
            "model_call_failed",
            str(raw_response.get("error") or "model caller reported failure"),
        )
    for key in ("text", "content", "output_text"):
        value = raw_response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ModelActionParseError("invalid_model_action_json", "model caller did not return text")


def _projection_document(projection: SharedStateProjection | None) -> dict[str, Any]:
    if projection is None:
        return {}
    return {
        "mission_state": _jsonable(projection.mission_state),
        "resolution_state": _jsonable(projection.resolution_state),
        "latest_refs": dict(projection.latest_refs),
        "active_item_id": projection.active_item_id,
    }


def _turn_input_document(composed_input: ComposedTurnInput) -> dict[str, Any]:
    return {
        "blocks": [
            {
                "content": block.content,
                "metadata": _jsonable(block.metadata),
            }
            for block in composed_input.blocks
        ],
        "surface_payloads": {
            surface_id: _jsonable(payload)
            for surface_id, payload in composed_input.surface_payloads.items()
        },
        "tool_ids": list(composed_input.tool_handlers.keys()),
    }


def _turn_snapshot(composed_input: ComposedTurnInput) -> dict[str, Any]:
    return {
        "surface_payloads": {
            surface_id: _jsonable(payload)
            for surface_id, payload in composed_input.surface_payloads.items()
        },
        "tool_ids": list(composed_input.tool_handlers.keys()),
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="python")  # type: ignore[call-arg]
        return _jsonable(dumped)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(raw_value) for key, raw_value in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=str)]
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_json_bool(payload: Mapping[str, Any], key: str) -> bool:
    if key not in payload:
        raise ModelActionParseError("invalid_model_action_json", f"{key} is required and must be a boolean")
    value = payload.get(key)
    if type(value) is not bool:
        raise ModelActionParseError("invalid_model_action_json", f"{key} must be a JSON boolean")
    return value
