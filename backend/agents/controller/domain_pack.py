"""Deed-to-IR domain pack — implements the 9-hook DomainPack protocol.

This adapter wraps deed controller machinery and plugs into the orchestration
kernel. The orchestration kernel is the sole runtime for deed_to_ir; the legacy
controller loop is retired (guarded by PLATTERA_ENABLE_LEGACY_CONTROLLERS).

Hook ownership:
- Domain pack owns: bootstrap_context, transcript, proposal state, refusal/autofill,
  phase_hint inference, context packet assembly, LLM proposal, argument validation.
- Kernel owns: active_focus_key, focus_stagnation_streak, HitlState, no_progress_streak,
  evidence_signal_counter (loop_memory), invalid_plan_strikes, TerminalDecision.

Per-iteration ephemeral cross-hook state:
  _iter_context_packet: set in hook 4 (build_focus_packet), consumed in hook 5/6.
  _iter_proposal: set in hook 5 (resolve_move), consumed in hook 6 (compile_move).
These are reset at the start of each iteration's hook 4 call.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from agent_kernel.models import (
    ActionType,
    KernelRefusal,
    KernelSessionStartRequest,
    KernelSessionStartResult,
)

from harness.orchestration_kernel.contracts import (
    ClosureEvaluation,
    FocusPacket,
    IntegrationResult,
    MoveDecision,
    MoveExecutionPlan,
    OrchestratorContext,
    ProgressMetrics,
    RefreshResult,
    WorkStateProjection,
)
from harness.terminal_taxonomy import classify_controller_terminal

from .controller_bootstrap import _bootstrap_deed_span_index_from_transcript_seeds, _build_bootstrap_context
from .controller_context import _build_context_packet, _compact_gap_summary
from .controller_guardrails import (
    _infer_phase_hint,
    _latest_refs_summary,
    _read_str,
)
from .controller_proposals import (
    _autofill_known_args,
    _normalize_controller_notes,
    _propose_next_step,
    _propose_refusal_repair_step,
    _refusal_repair_request,
    _validate_controller_inputs,
)
from .controller_transcript import _append_event, _log_controller_event
from .contracts import (
    KernelStepProposal,
    coerce_action_type,
    validate_action_args,
)

_LOG = logging.getLogger(__name__)

# Action types that gather/inspect evidence without modifying artifacts.
# Used in D3 to classify move_type as "gather_more_evidence" vs "apply_edit_plan".
_DEED_EVIDENCE_GATHERING_ACTION_TYPES = frozenset({
    "open_artifact",
    "open_text_spans",
    "retrieve_evidence",
    "hydrate_deed",
    "summarize_status",
})


class DeedToIRDomainPack:
    """Deed-to-IR implementation of the DomainPack protocol.

    Wraps existing deed controller modules. The pack holds its own mutable
    view of the session dashboard (``_started``) and projects progress into
    shared kernel contracts via hook return values.

    Construction: one instance per loop run.
    Must be constructed AFTER ``session_manager.start_session()`` has been
    called; the caller passes the resulting ``KernelSessionStartResult`` in.
    """

    def __init__(
        self,
        *,
        start_request: KernelSessionStartRequest,
        started: KernelSessionStartResult,
        model: str,
        llm_client: Any,  # NextStepLLMClient Protocol
        request_id_prefix: str,
    ) -> None:
        self._start_request = start_request
        self._started = started  # mutable — dashboard updated after each step
        self._model = model
        self._llm_client = llm_client
        self._request_id_prefix = request_id_prefix

        # Bootstrap context — populated in orient.
        self._bootstrap_context: dict[str, Any] = {}

        # Controller event transcript (mirrors legacy controller pattern).
        self._transcript: list[dict[str, Any]] = []

        # Latest artifact refs — updated in refresh from loop_memory and steps.
        self._latest_refs: dict[str, Any] = {}

        # Phase hint derived from dashboard.
        self._phase_hint: str = "author_ir"

        # Refusal / guardrail tracking — consumed in compile_move.
        self._last_refusal: Any | None = None
        self._last_refusal_action_type_raw: str | None = None
        self._pending_refusal_repair: dict[str, Any] | None = None
        self._refusal_streak: int = 0
        self._previous_refusal_signature: str | None = None

        # Run summary (for refusal loop diagnostics).
        self._run_summary_ref: str | None = None
        self._run_summary_excerpt: str | None = None
        self._recent_digest_memory: list[dict[str, Any]] = []

        # Iteration de-dup guardrails.
        self._repeated_inspection_ref: str | None = None
        self._repeated_inspection_count: int = 0
        self._repeated_span_open_signature: str | None = None
        self._repeated_span_open_count: int = 0
        self._semantic_span_repair_signature: str | None = None
        self._semantic_span_repair_count: int = 0

        # Progress baselines for hook 7.
        self._prev_refs_fingerprint: str | None = None
        self._prev_dashboard_snapshot: dict[str, Any] | None = None

        # Consecutive failure streaks for D1/D2 stop-condition alignment.
        # Incremented on parse fail (hook 5) or compile fail (hook 6); reset on success.
        self._parse_fail_streak: int = 0
        self._compile_fail_streak: int = 0

        # Ephemeral per-iteration state (hook 4 → hook 5 → hook 6).
        self._iter_context_packet: dict[str, Any] | None = None
        self._iter_proposal: KernelStepProposal | None = None

    # -------------------------------------------------------------------------
    # Hook 1 — orient
    # -------------------------------------------------------------------------

    def orient(self, context: OrchestratorContext) -> None:
        """Phase 1 — Build bootstrap context and seed span index.

        Builds the bootstrap_context dict from the start_request metadata,
        then attempts to bootstrap a deed-span index from transcript seeds
        (no-op when deed_text_full or seed bundle is unavailable).
        Runs once at loop start.
        """
        session_manager = context.session_manager
        session_id = context.session_id
        request_id_prefix = context.request_id_prefix

        self._bootstrap_context = _build_bootstrap_context(self._start_request)

        _LOG.info(
            "DEED_DOMAIN_PACK orient ► request_id=%s dossier=%s",
            request_id_prefix,
            self._bootstrap_context.get("dossier_id"),
        )

        # Bootstrap deed span index from transcript seeds (opportunistic).
        seed_result = _bootstrap_deed_span_index_from_transcript_seeds(
            session_manager=session_manager,
            session_id=session_id,
            request_id=request_id_prefix,
            bootstrap_context=self._bootstrap_context,
        )
        if seed_result is not None and seed_result.dashboard is not None:
            self._started.dashboard = seed_result.dashboard
            self._latest_refs = seed_result.dashboard.latest_refs.model_dump(mode="json")
            _LOG.info("DEED_DOMAIN_PACK orient_seed_bootstrap ► refs=%s", sorted(self._latest_refs))
        else:
            if self._started.dashboard is not None:
                self._latest_refs = self._started.dashboard.latest_refs.model_dump(mode="json")

        _append_event(
            self._transcript,
            event_type="deed_domain_orient",
            detail="orient_complete",
            payload={
                "dossier_id": self._bootstrap_context.get("dossier_id"),
                "has_deed_text": bool(self._bootstrap_context.get("deed_text_full")),
                "initial_refs": list(self._latest_refs.keys()),
            },
        )

    # -------------------------------------------------------------------------
    # Hook 2 — refresh
    # -------------------------------------------------------------------------

    def refresh(self, context: OrchestratorContext) -> RefreshResult:
        """Phase 2 — Mechanical refresh: update latest_refs from kernel's loop_memory.

        No LLM audit call needed for deed. Reads kernel-owned latest_refs
        (updated by kernel after phase-6 execution) and updates local state.
        Also re-derives phase_hint from the latest dashboard snapshot.
        """
        # Kernel updates loop_memory.latest_refs after each phase-6 step.
        # Use those as authoritative refs; fall back to our own tracked refs.
        kernel_refs = dict(context.loop_memory.latest_refs) if context.loop_memory.latest_refs else {}
        merged_refs = {**self._latest_refs, **kernel_refs}
        self._latest_refs = merged_refs

        # Re-derive phase hint from current dashboard snapshot.
        snapshot = self._current_dashboard_snapshot(context)
        self._phase_hint = _infer_phase_hint(snapshot)

        _LOG.info(
            "DEED_DOMAIN_PACK refresh ► iter=%s phase_hint=%s refs=%s",
            context.loop_memory.iterations,
            self._phase_hint,
            sorted(merged_refs),
        )

        return RefreshResult(
            latest_refs=merged_refs,
            execution_succeeded=True,
        )

    # -------------------------------------------------------------------------
    # Hook 3 — project
    # -------------------------------------------------------------------------

    def project(self, context: OrchestratorContext) -> WorkStateProjection:
        """Phase 3 — Project deed authority into Work-State sub-surfaces.

        Produces one work item per gap kind (derived from gap_summary.top_gap_kinds)
        plus a finalize item when claimability is ready, and a phase-fallback item
        when no gaps exist. All items use ``focus_key`` (required by kernel's
        _select_focus). Gap items use stable keys so focus-stagnation tracking works
        across iterations.
        """
        snapshot = self._current_dashboard_snapshot(context)
        claimability = snapshot.get("claimability") or {}
        claimable_ready = bool(claimability.get("claimable_ready"))
        gap_summary = _compact_gap_summary(snapshot.get("gap_summary"))
        top_gap_kinds: list[str] = gap_summary.get("top_gap_kinds") or []

        work_items: list[dict[str, Any]] = []
        ranked: list[dict[str, Any]] = []

        # Highest priority: declare-done focus when claimability gate is open.
        if claimable_ready:
            declare_item: dict[str, Any] = {
                "focus_key": "phase:declare_candidate",
                "priority": 0,
                "status": "open",
                "phase_hint": "declare_candidate",
            }
            work_items.append(declare_item)
            ranked.append(declare_item)

        # Per-gap-kind work items (priority ordered as given by gap_summary).
        for i, kind in enumerate(top_gap_kinds[:8]):
            gap_item: dict[str, Any] = {
                "focus_key": f"gap:{kind}",
                "priority": i + 1,
                "status": "open",
                "phase_hint": self._phase_hint,
                "gap_kind": kind,
            }
            work_items.append(gap_item)
            ranked.append(gap_item)

        # Fallback: when no gaps and not claimable, use phase hint as focus key.
        if not ranked:
            fallback: dict[str, Any] = {
                "focus_key": f"phase:{self._phase_hint}",
                "priority": 1,
                "status": "open",
                "phase_hint": self._phase_hint,
            }
            work_items.append(fallback)
            ranked.append(fallback)

        return WorkStateProjection(
            work_item_collection=work_items,
            blocker_surface=[],
            closure_posture_summary={
                "phase_hint": self._phase_hint,
                "claimable_ready": claimable_ready,
                "gap_count": len(top_gap_kinds),
            },
            ranked_work_item_list=ranked,
        )

    # -------------------------------------------------------------------------
    # Hook 4 — build_focus_packet
    # -------------------------------------------------------------------------

    def build_focus_packet(self, context: OrchestratorContext, focus_key: str) -> FocusPacket:
        """Phase 5a — Assemble observation (context packet) for the active focus item.

        Builds the full deed-to-IR context packet using the existing
        _build_context_packet machinery. The packet includes bootstrap_context,
        dashboard progress (with up-to-date refs), transcript, phase_hint, etc.
        """
        # Reset per-iteration ephemeral state.
        self._iter_context_packet = None
        self._iter_proposal = None

        snapshot = self._current_dashboard_snapshot(context)
        tool_menu = list(self._started.tool_menu or [])

        context_packet = _build_context_packet(
            session_id=context.session_id,
            tool_menu=tool_menu,
            bootstrap_context=self._bootstrap_context,
            dashboard=snapshot,
            transcript=self._transcript,
            last_refusal=self._last_refusal,
            last_refusal_action_type_raw=self._last_refusal_action_type_raw,
            last_step_result=None,  # kernel owns execution; domain pack doesn't track step results
            run_summary_ref=self._run_summary_ref,
            run_summary_excerpt=self._run_summary_excerpt,
            phase_hint=self._phase_hint,
            recent_digest_memory=self._recent_digest_memory,
        )
        # D2: inject focus-scoped summary so the LLM sees the specific gap to address.
        if isinstance(context_packet, dict):
            gap_summary = _compact_gap_summary(snapshot.get("gap_summary"))
            context_packet["focus_scope"] = _build_deed_focus_scope(focus_key, gap_summary)
            # Inject rejected graph context from last retryable step refusal if available.
            # The kernel surfaces this via loop_memory.last_step_refusal_record so the LLM
            # can correct a bad graph proposal rather than repeating the same mistake.
            _step_refusal_rec = context.loop_memory.last_step_refusal_record
            if isinstance(_step_refusal_rec, dict):
                _inline = _step_refusal_rec.get("outputs_inline")
                if isinstance(_inline, dict) and (
                    "rejected_graph_summary" in _inline or "rejected_graph_artifact_ref" in _inline
                ):
                    _refusal_payload = context_packet.get("last_refusal") or {}
                    if isinstance(_refusal_payload, dict):
                        if "rejected_graph_summary" in _inline:
                            _refusal_payload["rejected_graph_summary"] = _inline["rejected_graph_summary"]
                        if "rejected_graph_artifact_ref" in _inline:
                            _refusal_payload["rejected_graph_artifact_ref"] = _inline["rejected_graph_artifact_ref"]
                        if not _refusal_payload.get("reason_code"):
                            _step_kr = _step_refusal_rec.get("outputs_inline", {}).get("kernel_refusal", {})
                            _refusal_payload["reason_code"] = (
                                _step_kr.get("reason_code") if isinstance(_step_kr, dict) else "draft_ir_graph_validation_failed"
                            )
                        context_packet["last_refusal"] = _refusal_payload
        self._iter_context_packet = context_packet

        return FocusPacket(
            focus_key=focus_key,
            domain_packet=context_packet,
        )

    # -------------------------------------------------------------------------
    # Hook 5 — resolve_move
    # -------------------------------------------------------------------------

    def resolve_move(self, context: OrchestratorContext, focus_packet: FocusPacket) -> MoveDecision:
        """Phase 5b — Call LLM to propose next deed controller step.

        Uses _propose_next_step to get a KernelStepProposal from the LLM.
        Translates the proposal into a MoveDecision for the kernel.
        """
        observation = focus_packet.domain_packet

        # Prefer refusal repair if pending.
        if self._pending_refusal_repair is not None:
            repair_request = self._pending_refusal_repair
            self._pending_refusal_repair = None
            proposal = _propose_refusal_repair_step(
                llm_client=self._llm_client,
                model=self._model,
                observation=observation,
                transcript=self._transcript,
                repair_request=repair_request,
            )
        else:
            proposal = _propose_next_step(
                llm_client=self._llm_client,
                model=self._model,
                observation=observation,
                transcript=self._transcript,
            )

        if proposal is None:
            self._parse_fail_streak += 1
            self._compile_fail_streak = 0
            _LOG.warning(
                "DEED_DOMAIN_PACK resolve_move_parse_failed ► iter=%s streak=%s",
                context.loop_memory.iterations,
                self._parse_fail_streak,
            )
            return MoveDecision(
                move_type="mark_blocked",
                focus_key=focus_packet.focus_key,
                rationale="llm_parse_failed_no_valid_proposal",
                domain_move_payload={"reason": "proposal_parse_failed"},
            )

        # Successful proposal — reset parse-fail streak.
        self._parse_fail_streak = 0
        self._iter_proposal = proposal
        action_type_raw = str(proposal.action_type or "").strip().lower()

        if action_type_raw == ActionType.DECLARE_DONE.value:
            return MoveDecision(
                move_type="apply_edit_plan",
                focus_key=focus_packet.focus_key,
                rationale=proposal.why,
                domain_move_payload={"proposal": proposal, "declare_done": True},
            )

        # D3: classify move as evidence-gathering vs apply so the kernel logs intent
        # and future progress evaluation can distinguish exploration from execution.
        move_type = (
            "gather_more_evidence"
            if action_type_raw in _DEED_EVIDENCE_GATHERING_ACTION_TYPES
            else "apply_edit_plan"
        )
        return MoveDecision(
            move_type=move_type,
            focus_key=focus_packet.focus_key,
            rationale=proposal.why,
            domain_move_payload={"proposal": proposal, "declare_done": False},
        )

    # -------------------------------------------------------------------------
    # Hook 6 — compile_move
    # -------------------------------------------------------------------------

    def compile_move(self, context: OrchestratorContext, move_decision: MoveDecision) -> MoveExecutionPlan:
        """Phase 5c — Validate and compile proposal into an execution-ready plan.

        Applies autofill, validates action args, computes idempotency key.
        Returns MoveExecutionPlan. Sets declare_done_flag for DECLARE_DONE actions.
        If validation fails, falls back to mark_blocked by returning skip_execution=True.
        """
        payload = move_decision.domain_move_payload or {}
        proposal = payload.get("proposal")
        declare_done = bool(payload.get("declare_done"))

        if not isinstance(proposal, KernelStepProposal):
            # No valid proposal (move_type was mark_blocked) — skip execution.
            _LOG.warning(
                "DEED_DOMAIN_PACK compile_move_no_proposal ► iter=%s",
                context.loop_memory.iterations,
            )
            # Don't increment compile_fail_streak here — parse_fail_streak covers this case.
            return MoveExecutionPlan(
                action_type=ActionType.OPEN_ARTIFACT,
                action_inputs={},
                idempotency_key=f"skip-{context.loop_memory.iterations}-no_proposal",
                skip_execution=True,
            )

        if declare_done:
            # The kernel will terminate with "completed" when declare_done_flag=True.
            return MoveExecutionPlan(
                action_type=ActionType.DECLARE_DONE,
                action_inputs=dict(proposal.args),
                idempotency_key=self._compute_idempotency_key(
                    context.session_id, context.loop_memory.iterations,
                    ActionType.DECLARE_DONE.value, proposal.args,
                ),
                declare_done_flag=True,
            )

        action_type = coerce_action_type(str(proposal.action_type or ""))
        if action_type is None:
            self._compile_fail_streak += 1
            _LOG.warning(
                "DEED_DOMAIN_PACK compile_move_invalid_action ► iter=%s action=%s streak=%s",
                context.loop_memory.iterations,
                proposal.action_type,
                self._compile_fail_streak,
            )
            return MoveExecutionPlan(
                action_type=ActionType.OPEN_ARTIFACT,
                action_inputs={},
                idempotency_key=f"skip-{context.loop_memory.iterations}-invalid_action",
                skip_execution=True,
            )

        snapshot = self._current_dashboard_snapshot(context)
        proposal_inputs = dict(proposal.args)
        proposal_inputs, _autofill_applied = _autofill_known_args(
            action_type=action_type,
            args=proposal_inputs,
            bootstrap_context=self._bootstrap_context,
            dashboard=snapshot,
            context_packet=self._iter_context_packet or {},
        )

        # Validate payload size.
        payload_refusal = _validate_controller_inputs(proposal_inputs)
        if payload_refusal is not None:
            self._compile_fail_streak += 1
            self._last_refusal = payload_refusal
            self._last_refusal_action_type_raw = action_type.value
            _LOG.warning(
                "DEED_DOMAIN_PACK compile_move_payload_refusal ► iter=%s reason=%s streak=%s",
                context.loop_memory.iterations,
                payload_refusal.reason_code,
                self._compile_fail_streak,
            )
            return MoveExecutionPlan(
                action_type=ActionType.OPEN_ARTIFACT,
                action_inputs={},
                idempotency_key=f"skip-{context.loop_memory.iterations}-payload_too_large",
                skip_execution=True,
            )

        cleaned_inputs, args_reason, args_missing = validate_action_args(
            action_type=action_type,
            args=proposal_inputs,
        )
        if cleaned_inputs is None:
            self._compile_fail_streak += 1
            refusal = KernelRefusal(
                reason_code=args_reason or f"{action_type.value}_inputs_invalid",
                missing_inputs=args_missing or [],
                retryable=True,
            )
            self._last_refusal = refusal
            self._last_refusal_action_type_raw = action_type.value
            # Build repair request for next iteration.
            self._pending_refusal_repair = _refusal_repair_request(
                action_type_raw=action_type.value,
                refusal=refusal,
                bootstrap_context=self._bootstrap_context,
                context_inputs=self._iter_context_packet.get("inputs", {}) if self._iter_context_packet else {},
            )
            _LOG.warning(
                "DEED_DOMAIN_PACK compile_move_args_invalid ► iter=%s reason=%s streak=%s",
                context.loop_memory.iterations,
                args_reason,
                self._compile_fail_streak,
            )
            return MoveExecutionPlan(
                action_type=ActionType.OPEN_ARTIFACT,
                action_inputs={},
                idempotency_key=f"skip-{context.loop_memory.iterations}-args_invalid",
                skip_execution=True,
            )

        # Valid plan — reset refusal and compile-fail state.
        self._last_refusal = None
        self._last_refusal_action_type_raw = None
        self._refusal_streak = 0
        self._compile_fail_streak = 0

        idempotency_key = self._compute_idempotency_key(
            context.session_id,
            context.loop_memory.iterations,
            action_type.value,
            cleaned_inputs,
        )
        return MoveExecutionPlan(
            action_type=action_type,
            action_inputs=cleaned_inputs,
            idempotency_key=idempotency_key,
        )

    # -------------------------------------------------------------------------
    # Hook 7 — supply_progress_metrics
    # -------------------------------------------------------------------------

    def supply_progress_metrics(self, context: OrchestratorContext) -> ProgressMetrics:
        """Phase 7 — Supply deed-specific progress metrics for the shared evaluator.

        Uses fingerprint comparison of latest_refs to detect new evidence.
        Pending_refresh is kernel-owned; we read it from context.loop_memory.
        """
        current_refs = dict(self._latest_refs)
        # Merge in any kernel-updated refs.
        kernel_refs = dict(context.loop_memory.latest_refs) if context.loop_memory.latest_refs else {}
        current_refs.update(kernel_refs)

        current_refs_fingerprint = _fingerprint(current_refs)

        # Compute current blocking signature from the live dashboard snapshot.
        # Must be computed before gaps_changed to avoid UnboundLocalError.
        snapshot = self._current_dashboard_snapshot(context)
        gap_summary = _compact_gap_summary(snapshot.get("gap_summary"))
        blocking_sig = _fingerprint(gap_summary.get("top_gap_kinds") or [])

        # D4: also treat gap_summary changes as evidence — when a gap resolves, the
        # blocking signature changes and that counts as progress even if refs are static.
        refs_changed = current_refs_fingerprint != self._prev_refs_fingerprint
        gaps_changed = (
            self._prev_dashboard_snapshot is not None
            and blocking_sig != _fingerprint(
                _compact_gap_summary(self._prev_dashboard_snapshot.get("gap_summary")).get("top_gap_kinds") or []
            )
        )
        # A successful step execution (pending_refresh=True) always counts as evidence
        # for deed — e.g. open_text_spans returns inline spans (no persistent ref) but
        # the LLM has new information. Without this, inline-only steps cause stagnation.
        step_executed = bool(context.loop_memory.pending_refresh)
        new_evidence = refs_changed or gaps_changed or step_executed

        prev_blocking_sig = None
        prev_blocking_count = None
        if self._prev_dashboard_snapshot is not None:
            prev_gap = _compact_gap_summary(self._prev_dashboard_snapshot.get("gap_summary"))
            prev_blocking_sig = _fingerprint(prev_gap.get("top_gap_kinds") or [])
            prev_blocking_count = len(prev_gap.get("top_gap_kinds") or [])

        current_blocking_count = len(gap_summary.get("top_gap_kinds") or [])

        metrics = ProgressMetrics(
            previous_finding_signature=self._prev_refs_fingerprint,
            current_finding_signature=current_refs_fingerprint,
            previous_blocking_signature=prev_blocking_sig,
            current_blocking_signature=blocking_sig,
            previous_blocking_count=prev_blocking_count,
            current_blocking_count=current_blocking_count,
            new_evidence_signal=new_evidence,
            pending_feedback_prompt_id=None,  # deed has no HITL path in v1
            # Deed does not use the pending_refresh evaluation path (no audit baseline);
            # new_evidence_signal already incorporates step execution signal.
            pending_refresh=False,
            refresh_baseline_blocking_count=None,
            refresh_baseline_blocking_signature=None,
        )

        # Advance baselines for next iteration.
        self._prev_refs_fingerprint = current_refs_fingerprint
        self._prev_dashboard_snapshot = dict(snapshot)
        self._latest_refs = current_refs

        return metrics

    # -------------------------------------------------------------------------
    # Hook 8 — supply_closure_rules
    # -------------------------------------------------------------------------

    def supply_closure_rules(self, context: OrchestratorContext) -> ClosureEvaluation:
        """Phase 8 — Evaluate deed closure conditions.

        Deed completion is signalled via declare_done_flag in compile_move (hook 6).
        This hook provides a fallback terminal evaluation using the dashboard's
        failure_classification and claimability status.
        """
        # D1 — parse-fail streak: repeated LLM parse failures → blocked/proposal_parse_failed.
        if self._parse_fail_streak >= 2:
            _LOG.warning(
                "DEED_DOMAIN_PACK supply_closure_rules_parse_fail_terminal ► streak=%s",
                self._parse_fail_streak,
            )
            return ClosureEvaluation(
                domain_complete=False,
                domain_terminal_class="blocked",
                closure_reason_code="proposal_parse_failed",
                open_items_summary=f"parse_fail_streak:{self._parse_fail_streak}",
            )

        # D2 — compile-fail streak: repeated invalid proposals → blocked/invalid_refused.
        if self._compile_fail_streak >= 3:
            _LOG.warning(
                "DEED_DOMAIN_PACK supply_closure_rules_compile_fail_terminal ► streak=%s",
                self._compile_fail_streak,
            )
            return ClosureEvaluation(
                domain_complete=False,
                domain_terminal_class="blocked",
                closure_reason_code="invalid_refused",
                open_items_summary=f"compile_fail_streak:{self._compile_fail_streak}",
            )

        snapshot = self._current_dashboard_snapshot(context)
        failure_cls = snapshot.get("failure_classification") or {}
        stop_reason = _read_str(failure_cls.get("stop_reason"))
        reason_code = _read_str(failure_cls.get("reason_code"))

        # Only emit terminal if session has a hard stop signal.
        if stop_reason and stop_reason not in {"", "none"}:
            taxonomy = classify_controller_terminal(
                stop_reason=stop_reason,
                terminal_outcome=None,
                success=stop_reason == "completed",
                reason_code=reason_code,
            )
            is_done = taxonomy.terminal_class == "completed"
            return ClosureEvaluation(
                domain_complete=is_done,
                domain_terminal_class=taxonomy.terminal_class,
                closure_reason_code=reason_code or stop_reason,
                open_items_summary=f"stop_reason:{stop_reason}",
            )

        # Default: still working — let the kernel manage budget and stagnation.
        # domain_terminal_class is irrelevant when domain_complete=False and
        # _is_cannot_proceed(reason_code) is False (which "deed_in_progress" guarantees).
        # "blocked" is used here only as the required sentinel; it does NOT mean cannot-proceed.
        return ClosureEvaluation(
            domain_complete=False,
            domain_terminal_class="blocked",
            closure_reason_code="deed_in_progress",
            open_items_summary=f"phase:{self._phase_hint}",
        )

    # -------------------------------------------------------------------------
    # Hook 9 — integrate_feedback
    # -------------------------------------------------------------------------

    def integrate_feedback(
        self, context: OrchestratorContext, feedback_response: dict[str, Any]
    ) -> IntegrationResult:
        """Pre-phase 2 — Deed has no HITL path in v1. Always returns integrated=False."""
        _LOG.info(
            "DEED_DOMAIN_PACK integrate_feedback_noop ► iter=%s",
            context.loop_memory.iterations,
        )
        return IntegrationResult(
            integrated=False,
            integration_summary="deed_no_hitl_path_v1",
        )

    # -------------------------------------------------------------------------
    # Domain runtime state (for result adaptation)
    # -------------------------------------------------------------------------

    def build_domain_runtime_state(self) -> dict[str, Any]:
        """Return opaque domain state dict for the mission-runtime result adapter."""
        snapshot = self._started.dashboard.model_dump(mode="json") if self._started.dashboard else {}
        return {
            "deed_phase_hint": self._phase_hint,
            "latest_refs": self._latest_refs,
            "failure_classification": snapshot.get("failure_classification"),
            "claimability": snapshot.get("claimability"),
        }

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _current_dashboard_snapshot(self, context: OrchestratorContext) -> dict[str, Any]:
        """Build a dashboard dict with up-to-date latest_refs from loop_memory."""
        if self._started.dashboard is None:
            return {}
        snapshot = dict(self._started.dashboard.model_dump(mode="json"))
        # Patch latest_refs with kernel's up-to-date version.
        kernel_refs = context.loop_memory.latest_refs or {}
        # _latest_refs_summary expects {key: {"artifact_path": path}} format.
        # loop_memory.latest_refs is already in that format (from dashboard.model_dump).
        if kernel_refs:
            snapshot["latest_refs"] = dict(kernel_refs)
        elif self._latest_refs:
            # Convert our {key: path_string} to {key: {"artifact_path": path_string}}.
            snapshot["latest_refs"] = {
                k: {"artifact_path": v}
                for k, v in self._latest_refs.items()
                if isinstance(v, str)
            }
        return snapshot

    @staticmethod
    def _compute_idempotency_key(
        session_id: str,
        iteration: int,
        action_type: str,
        inputs: dict[str, Any],
    ) -> str:
        normalized = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(
            f"{session_id}|{iteration}|{action_type}|{normalized}".encode("utf-8")
        ).hexdigest()[:24]
        return f"deed-{digest}"


def _build_deed_focus_scope(focus_key: str, gap_summary: dict[str, Any]) -> dict[str, Any]:
    """Build a focus-scoped summary for inclusion in the FocusPacket domain_packet.

    Gives the LLM a targeted description of which gap kind (or phase) the current
    focus key represents, plus the relevant counts and reason codes from gap_summary.
    """
    if focus_key.startswith("gap:"):
        kind = focus_key[4:]
        counts = gap_summary.get("gap_counts_by_kind") or {}
        reason_codes = gap_summary.get("top_reason_codes") or []
        return {
            "focus_key": focus_key,
            "focus_type": "gap",
            "gap_kind": kind,
            "gap_count": counts.get(kind),
            "relevant_reason_codes": [rc for rc in reason_codes[:6] if kind.lower() in rc.lower() or not reason_codes],
            "all_top_reason_codes": reason_codes[:4],
        }
    if focus_key.startswith("phase:"):
        phase = focus_key[6:]
        return {
            "focus_key": focus_key,
            "focus_type": "phase",
            "phase_hint": phase,
        }
    return {"focus_key": focus_key, "focus_type": "unknown"}


def _fingerprint(value: Any) -> str:
    try:
        serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except Exception:
        serialized = str(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
