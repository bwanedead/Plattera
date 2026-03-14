"""Transcript-edit domain pack — implements the 9-hook DomainPack protocol.

This adapter wraps existing transcript-edit modules to plug into the orchestration kernel.
It is NOT a replacement for the legacy controller loop; both coexist behind a feature flag.

Hook ownership:
- Domain pack owns: decision_ledger, blocker_registry, evidence assembly, move resolution,
  move compilation, progress metric derivation, closure evaluation, feedback integration.
- Kernel owns: active_focus_key, focus_stagnation_streak, HitlState, no_progress_streak,
  evidence_signal_counter (loop_memory), invalid_plan_strikes, TerminalDecision.

Per-iteration ephemeral state (reset in hook 2):
  _iter_findings_summary, _iter_planning_findings, _iter_source_hash,
  _iter_finding_signature, _iter_blocking_signature, _iter_blocking_count
These are used by hook 7 to supply ProgressMetrics.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable

from agent_kernel.models import ActionType, KernelStepRequest, StepExecutionState

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

from .blocker_registry import (
    initialize_blocker_registry,
    select_primary_blocker,
    sync_registry_from_ledger,
    registry_snapshot_for_payload,
    blocker_health_snapshot,
)
from .contracts import TranscriptEditAgentRunRequest
from .decision_ledger import (
    initialize_decision_ledger,
    unresolved_closure_requirements,
    unresolved_mapping_blocking_requirements,
    update_ledger_from_orient_baseline,
    update_ledger_from_iteration,
    has_unresolved_target_scope_mapping_blocking_closure,
    ledger_snapshot_for_payload,
    choose_investigation_focus,
    list_external_context_injections,
)
from .decision_ledger_closure import unresolved_closure_requirements as _unresolved_closure_requirements
from .focus_packet import build_focus_packet
from .focus_resolver import resolve_focus_move
from .iteration_repair_focus import _select_focus_target
from .loop_runtime import (
    idempotency_key as _make_idempotency_key,
    read_step_outputs_inline,
    read_str,
    read_int,
)
from .loop_state import TranscriptEditLoopState
from .plan_interpretation import finding_signature
from .planner import TranscriptEditPlanPlanner
from .progress_evaluation import blocking_signature, blocking_unresolved_count
from .result_policy import (
    should_auto_promote_result,
    TranscriptEditFacts,
    has_unresolved_target_scope_mapping_blocking_closure as _policy_has_blocking,
)
from .state_projection import (
    derive_waiting_feedback_projection,
    sync_pending_feedback_cache_from_registry,
)
from .convention_situating import situate_document_convention
from .blocker_registry import set_convention_context
from .terminalization import derive_mission_runtime_summary

_LOG = logging.getLogger(__name__)

# Minimum iterations guard — domain pack checks this in hook 8 before signaling complete.
_DEFAULT_MIN_ITERATIONS_BEFORE_COMPLETE = 1


class TranscriptEditDomainPack:
    """Transcript-edit implementation of the DomainPack protocol.

    Wraps existing transcript-edit modules. The pack holds its own authoritative
    domain state (TranscriptEditLoopState) and projects into shared kernel contracts
    via hook return values.

    Construction: one instance per loop run.
    """

    def __init__(
        self,
        *,
        request: TranscriptEditAgentRunRequest,
        session_id: str,
        request_id_prefix: str,
        planner: TranscriptEditPlanPlanner | None = None,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
        loop_model: str = "gpt-5.2",
        initial_state: TranscriptEditLoopState | None = None,
    ) -> None:
        self._request = request
        self._session_id = session_id
        self._request_id_prefix = request_id_prefix
        self._planner = planner or TranscriptEditPlanPlanner()
        self._progress_cb = progress_cb
        self._loop_model = loop_model
        # Authoritative domain state; initialized in orient hook or from initial_state.
        self._state: TranscriptEditLoopState = initial_state or TranscriptEditLoopState()
        # Per-iteration ephemeral state set in hook 2, consumed in hook 7.
        self._iter_finding_signature: str = ""
        self._iter_blocking_signature: str = ""
        self._iter_blocking_count: int = 0
        self._iter_findings_summary: dict[str, Any] = {}
        self._iter_planning_findings: list[dict[str, Any]] = []
        self._iter_source_hash: str = ""
        # Previous-iteration progress baselines (updated at end of hook 7 call path).
        self._prev_finding_sig: str | None = None
        self._prev_blocking_sig: str | None = None
        self._prev_blocking_count: int | None = None
        self._prev_signal_counter: int = 0
        # Pending refresh baselines (set when pending_reaudit_after_apply).
        self._refresh_baseline_blocking_count: int | None = None
        self._refresh_baseline_blocking_sig: str | None = None

    # -------------------------------------------------------------------------
    # Hook 1 — orient
    # -------------------------------------------------------------------------

    def orient(self, context: OrchestratorContext) -> None:
        """Phase 1 — Pre-audit + orient baseline + initial domain state setup.

        Runs TX_AUDIT_TRANSCRIPT (pre-audit) then TX_ORIENT_AND_BASELINE.
        Initializes decision_ledger, blocker_registry, convention_context.
        Also handles resume state restoration when initial_state was provided.
        """
        request = self._request
        session_manager = context.session_manager
        session_id = context.session_id
        request_id_prefix = context.request_id_prefix

        # Initialize domain state if not already restored from resume.
        if not self._state.decision_ledger:
            self._state.decision_ledger = initialize_decision_ledger()
        if not self._state.blocker_registry:
            self._state.blocker_registry = initialize_blocker_registry(
                run_id=request_id_prefix,
                session_id=session_id,
                source_transcript_ref=request.source_transcript_ref,
            )

        # Pre-audit: source hash safety and advisory lints.
        pre_audit_inputs: dict[str, Any] = {"dossier_id": request.dossier_id}
        if self._state.current_transcript_ref:
            pre_audit_inputs["source_transcript_ref"] = self._state.current_transcript_ref
        elif request.source_text:
            pre_audit_inputs["source_text"] = request.source_text

        pre_audit = session_manager.step(
            KernelStepRequest(
                session_id=session_id,
                action_type=ActionType.TX_AUDIT_TRANSCRIPT,
                inputs=pre_audit_inputs,
                idempotency_key=_make_idempotency_key(
                    f"{request_id_prefix}:pre_audit", 0, pre_audit_inputs
                ),
            )
        )
        if pre_audit.execution_state == StepExecutionState.EXECUTED and pre_audit.dashboard:
            self._state.latest_refs = pre_audit.dashboard.latest_refs.model_dump(mode="json")
            inline = read_step_outputs_inline(pre_audit.step_record)
            src_ref = read_str(inline.get("tx_source_transcript_ref"))
            if src_ref:
                self._state.current_transcript_ref = src_ref
            self._pre_source_hash = read_str(inline.get("tx_source_transcript_hash")) or ""
        else:
            self._pre_source_hash = ""

        # Orient baseline: initializes decision_ledger from source material.
        orient_inputs: dict[str, Any] = {
            "dossier_id": request.dossier_id,
            "model": self._loop_model,
        }
        if self._state.current_transcript_ref:
            orient_inputs["source_transcript_ref"] = self._state.current_transcript_ref
        elif request.source_text:
            orient_inputs["source_text"] = request.source_text
        if request.candidate_refs:
            orient_inputs["candidate_refs"] = list(request.candidate_refs[:request.max_candidates_for_orient])
        elif request.candidate_texts:
            orient_inputs["candidate_texts"] = list(request.candidate_texts[:request.max_candidates_for_orient])

        orient = session_manager.step(
            KernelStepRequest(
                session_id=session_id,
                action_type=ActionType.TX_ORIENT_AND_BASELINE,
                inputs=orient_inputs,
                idempotency_key=_make_idempotency_key(
                    f"{request_id_prefix}:orient", 0, orient_inputs
                ),
            )
        )
        if orient.execution_state == StepExecutionState.EXECUTED and orient.dashboard:
            self._state.latest_refs = orient.dashboard.latest_refs.model_dump(mode="json")
            orient_inline = read_step_outputs_inline(orient.step_record)
            orient_src_ref = read_str(orient_inline.get("tx_source_transcript_ref"))
            if orient_src_ref:
                self._state.current_transcript_ref = orient_src_ref
            if read_str(orient_inline.get("tx_span_seeds_ref")):
                self._state.span_seeds_ref = read_str(orient_inline.get("tx_span_seeds_ref"))
            orient_items = [
                item
                for item in (orient_inline.get("tx_orient_items") or [])
                if isinstance(item, dict)
            ]
            self._state.decision_ledger = update_ledger_from_orient_baseline(
                ledger=self._state.decision_ledger,
                orient_items=orient_items,
            )
            self._state.convention_context = situate_document_convention(orient_items=orient_items)
            self._state.blocker_registry = set_convention_context(
                registry=self._state.blocker_registry,
                convention_context=self._state.convention_context,
            )

        # Sync blocker registry from ledger after orient.
        self._state.blocker_registry = sync_registry_from_ledger(
            registry=self._state.blocker_registry,
            decision_ledger=self._state.decision_ledger,
            run_id=request_id_prefix,
            session_id=session_id,
            source_transcript_ref=self._state.current_transcript_ref,
        )
        sync_pending_feedback_cache_from_registry(state=self._state)
        _LOG.info(
            "TX_DOMAIN_PACK orient_complete ► request_id=%s ledger_keys=%s",
            request_id_prefix,
            len(self._state.decision_ledger.get("items") or {}),
        )

    # -------------------------------------------------------------------------
    # Hook 2 — refresh
    # -------------------------------------------------------------------------

    def refresh(self, context: OrchestratorContext) -> RefreshResult:
        """Phase 2 — Per-iteration audit + ledger update.

        Runs TX_AUDIT_TRANSCRIPT, updates decision_ledger from findings,
        syncs blocker_registry, and stores per-iteration signatures for hook 7.
        """
        request = self._request
        session_manager = context.session_manager
        session_id = context.session_id
        iterations = context.loop_memory.iterations

        audit_inputs: dict[str, Any] = {"dossier_id": request.dossier_id}
        if self._state.current_transcript_ref:
            audit_inputs["source_transcript_ref"] = self._state.current_transcript_ref
        elif request.source_text:
            audit_inputs["source_text"] = request.source_text

        audit = session_manager.step(
            KernelStepRequest(
                session_id=session_id,
                action_type=ActionType.TX_AUDIT_TRANSCRIPT,
                inputs=audit_inputs,
                idempotency_key=_make_idempotency_key(
                    f"{self._request_id_prefix}:audit", iterations, audit_inputs
                ),
            )
        )
        if audit.execution_state != StepExecutionState.EXECUTED:
            reason = (
                audit.refusal.reason_code
                if audit.refusal is not None
                else "tx_audit_refused"
            )
            return RefreshResult(
                latest_refs=dict(self._state.latest_refs),
                execution_succeeded=False,
                refusal_reason=reason,
            )

        if audit.dashboard:
            self._state.latest_refs = audit.dashboard.latest_refs.model_dump(mode="json")

        inline = read_step_outputs_inline(audit.step_record)
        src_ref = read_str(inline.get("tx_source_transcript_ref"))
        if src_ref:
            self._state.current_transcript_ref = src_ref

        findings_summary = (
            inline.get("tx_validator_summary")
            if isinstance(inline.get("tx_validator_summary"), dict)
            else {}
        )
        top_findings = (
            inline.get("tx_top_findings")
            if isinstance(inline.get("tx_top_findings"), list)
            else []
        )
        src_hash = (
            read_str(inline.get("tx_source_transcript_hash"))
            or getattr(self, "_pre_source_hash", "")
        )

        # Update decision_ledger from audit findings.
        self._state.decision_ledger = update_ledger_from_iteration(
            ledger=self._state.decision_ledger,
            findings=top_findings,
        )
        self._state.blocker_registry = sync_registry_from_ledger(
            registry=self._state.blocker_registry,
            decision_ledger=self._state.decision_ledger,
            run_id=self._request_id_prefix,
            session_id=session_id,
            source_transcript_ref=self._state.current_transcript_ref,
        )
        sync_pending_feedback_cache_from_registry(state=self._state)

        # Derive and cache per-iteration signatures for hook 7.
        self._iter_finding_signature = finding_signature(
            summary=findings_summary, findings=top_findings
        )
        self._iter_blocking_signature = blocking_signature(self._state.decision_ledger)
        self._iter_blocking_count = blocking_unresolved_count(self._state.decision_ledger)
        self._iter_findings_summary = dict(findings_summary)
        self._iter_planning_findings = [f for f in top_findings if isinstance(f, dict)][:12]
        self._iter_source_hash = src_hash

        return RefreshResult(
            latest_refs=dict(self._state.latest_refs),
            execution_succeeded=True,
        )

    # -------------------------------------------------------------------------
    # Hook 3 — project
    # -------------------------------------------------------------------------

    def project(self, context: OrchestratorContext) -> WorkStateProjection:
        """Phase 3 — Project decision_ledger + blocker_registry into shared Work-State.

        Three persisted sub-surfaces: work_item_collection, blocker_surface,
        closure_posture_summary.
        One ephemeral sub-surface: ranked_work_item_list (consumed by phase 4).

        Focus state (active_focus_key, focus_stagnation_streak) is kernel-owned
        and NOT part of this projection.
        """
        ledger = self._state.decision_ledger
        registry = self._state.blocker_registry

        # Work-item collection: mapping-blocking unresolved items.
        unresolved = unresolved_mapping_blocking_requirements(ledger)
        work_item_collection = [
            {
                "focus_key": str(item.get("key") or "").strip().lower(),
                "state": str(item.get("state") or "unknown").strip().lower(),
                "mapping_blocking": bool(item.get("mapping_blocking")),
            }
            for item in unresolved
            if isinstance(item, dict) and str(item.get("key") or "").strip()
        ]

        # Blocker surface: active blockers from registry.
        blocker_rows = [
            dict(row)
            for row in list(registry.get("rows") or [])
            if isinstance(row, dict)
        ][:12]
        emergent_rows = [
            dict(row)
            for row in list((registry.get("emergent") or {}).get("rows") or [])
            if isinstance(row, dict)
        ][:6]
        blocker_surface = blocker_rows + emergent_rows

        # Closure posture summary.
        all_unresolved = _unresolved_closure_requirements(ledger)
        mapping_blocking = sum(
            1 for item in all_unresolved
            if isinstance(item, dict) and bool(item.get("mapping_blocking"))
        )
        closure_posture_summary = {
            "unresolved_count": len(all_unresolved),
            "mapping_blocking_count": mapping_blocking,
            "has_mapping_blocking_closure": mapping_blocking > 0,
            "closure_clear": mapping_blocking == 0,
        }

        # Ranked work-item list — ephemeral focus-selection hints for phase 4.
        # Uses transcript focus selection logic: choose_investigation_focus for fallback,
        # _select_focus_target for blocker-aware priority ordering.
        ranked: list[dict[str, Any]] = []
        if work_item_collection:
            fallback_focus = choose_investigation_focus(ledger) or {}
            feedback_payload = (
                dict(self._state.latest_feedback)
                if isinstance(self._state.latest_feedback, dict)
                else None
            )
            focus_target = _select_focus_target(
                decision_ledger=ledger,
                fallback_focus=fallback_focus,
                focus_feedback=feedback_payload,
                blocker_registry=registry,
            )
            primary_key = str(focus_target.get("decision_key") or "").strip().lower()
            if primary_key:
                ranked.append({
                    "focus_key": primary_key,
                    "state": "unresolved",
                    "priority": 0,
                    "focus_source": focus_target.get("focus_source", "primary"),
                })
            # Add remaining unresolved items after the primary.
            for item in work_item_collection:
                key = str(item.get("focus_key") or "").strip().lower()
                if key and key != primary_key:
                    ranked.append({**item, "priority": len(ranked)})

        return WorkStateProjection(
            work_item_collection=work_item_collection,
            blocker_surface=blocker_surface,
            closure_posture_summary=closure_posture_summary,
            ranked_work_item_list=ranked,
        )

    # -------------------------------------------------------------------------
    # Hook 4 — build_focus_packet
    # -------------------------------------------------------------------------

    def build_focus_packet(self, context: OrchestratorContext, focus_key: str) -> FocusPacket:
        """Phase 5a — Assemble evidence packet for the selected focus item."""
        state = self._state
        # Gather cached evidence surfaces.
        span_context = list(state.span_context_by_decision_key.get(focus_key) or [])
        image_verification = dict(
            state.image_verification_payload_by_decision_key.get(focus_key) or {}
        )
        visual_evidence = dict(state.visual_evidence_by_decision_key.get(focus_key) or {})
        feedback = (
            dict(state.latest_feedback)
            if isinstance(state.latest_feedback, dict)
            else None
        )
        src_hash = self._iter_source_hash or ""

        # Determine active blocker for this focus key from registry.
        active_blocker: dict[str, Any] | None = None
        for row in list(state.blocker_registry.get("rows") or []):
            if isinstance(row, dict):
                row_key = str(row.get("decision_key") or "").strip().lower()
                if row_key == focus_key:
                    active_blocker = dict(row)
                    break

        packet = build_focus_packet(
            decision_ledger=state.decision_ledger,
            decision_key=focus_key,
            active_emergent_blocker=active_blocker,
            blocker_registry=state.blocker_registry,
            source_transcript_ref=state.current_transcript_ref,
            source_transcript_hash=src_hash,
            span_context=span_context,
            image_verification_payload=image_verification,
            feedback=feedback,
            continuity_log=list(state.continuity_log or []),
            visual_evidence_state=visual_evidence,
        )
        return FocusPacket(focus_key=focus_key, domain_packet=packet)

    # -------------------------------------------------------------------------
    # Hook 5 — resolve_move
    # -------------------------------------------------------------------------

    def resolve_move(self, context: OrchestratorContext, focus_packet: FocusPacket) -> MoveDecision:
        """Phase 5b — Resolve the next move for the focus item."""
        packet = focus_packet.domain_packet
        move_payload = resolve_focus_move(
            focus_packet=packet,
            planner_client=self._planner,
            model=self._loop_model,
            findings_summary=self._iter_findings_summary,
            planning_findings=self._iter_planning_findings,
            max_invalid_plan_attempts=self._request.max_invalid_plan_attempts,
        )
        move_type = str(move_payload.get("move") or "mark_blocked").strip().lower()
        # Normalize move types to canonical forms.
        if move_type == "apply_edit_plan":
            normalized = "apply_edit_plan"
        elif move_type in ("gather_more_evidence", "investigate"):
            normalized = "gather_more_evidence"
        elif move_type in ("request_human_feedback", "request_feedback"):
            normalized = "request_human_feedback"
        elif move_type in ("mark_resolved_no_edit", "focus_item_not_mapping_blocking_unresolved"):
            normalized = "mark_resolved_no_edit"
        else:
            normalized = "mark_blocked"
        return MoveDecision(
            move_type=normalized,
            focus_key=focus_packet.focus_key,
            rationale=str(move_payload.get("reason") or "").strip() or None,
            domain_move_payload=dict(move_payload),
        )

    # -------------------------------------------------------------------------
    # Hook 6 — compile_move
    # -------------------------------------------------------------------------

    def compile_move(self, context: OrchestratorContext, move_decision: MoveDecision) -> MoveExecutionPlan:
        """Phase 5c — Compile move decision to a kernel-executable plan."""
        request = self._request
        payload = move_decision.domain_move_payload
        focus_key = move_decision.focus_key or ""
        iterations = context.loop_memory.iterations
        idempotency_prefix = f"{self._request_id_prefix}:{focus_key}:{iterations}"

        if move_decision.move_type == "apply_edit_plan":
            edit_plan = payload.get("edit_plan") if isinstance(payload.get("edit_plan"), dict) else {}
            inputs: dict[str, Any] = {
                "dossier_id": request.dossier_id,
                "edit_plan": edit_plan,
                "decision_key": focus_key,
            }
            if self._state.current_transcript_ref:
                inputs["source_transcript_ref"] = self._state.current_transcript_ref
            # Flag that we applied an edit — used for refresh baseline in hook 7.
            self._state.pending_reaudit_after_apply = True
            self._state.apply_reaudit_baseline_blocking_count = self._iter_blocking_count
            self._state.apply_reaudit_baseline_blocking_signature = self._iter_blocking_signature
            self._state.applied_any_edits = True
            return MoveExecutionPlan(
                action_type=ActionType.TX_APPLY_EDIT_PLAN,
                action_inputs=inputs,
                idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, inputs),
            )

        if move_decision.move_type == "gather_more_evidence":
            evidence_request = (
                payload.get("evidence_request")
                if isinstance(payload.get("evidence_request"), dict)
                else None
            )
            evidence_kind = str((evidence_request or {}).get("kind") or "open_spans").strip().lower()
            if evidence_kind == "open_spans":
                inputs = {
                    "dossier_id": request.dossier_id,
                    "decision_key": focus_key,
                }
                if self._state.current_transcript_ref:
                    inputs["source_transcript_ref"] = self._state.current_transcript_ref
                target = (evidence_request or {}).get("target") if isinstance((evidence_request or {}).get("target"), dict) else {}
                span_ids = [str(v) for v in list((target or {}).get("span_ids") or []) if str(v).strip()][:8]
                if span_ids:
                    inputs["span_ids"] = span_ids
                return MoveExecutionPlan(
                    action_type=ActionType.TX_OPEN_TRANSCRIPT_SPANS,
                    action_inputs=inputs,
                    idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, inputs),
                )
            # Default: re-audit as a fallback investigation step.
            inputs = {"dossier_id": request.dossier_id}
            if self._state.current_transcript_ref:
                inputs["source_transcript_ref"] = self._state.current_transcript_ref
            return MoveExecutionPlan(
                action_type=ActionType.TX_AUDIT_TRANSCRIPT,
                action_inputs=inputs,
                idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, inputs),
            )

        if move_decision.move_type == "request_human_feedback":
            feedback_prompt = payload.get("feedback_prompt") if isinstance(payload.get("feedback_prompt"), dict) else {}
            prompt_id = str(feedback_prompt.get("prompt_id") or _make_prompt_id(focus_key, iterations)).strip()
            # The domain pack stores the pending prompt for resume; kernel handles HitlState.
            self._state.pending_feedback_prompt_id = prompt_id
            self._state.pending_feedback_decision_key = focus_key
            self._state.pending_feedback_prompt = dict(feedback_prompt)
            sync_pending_feedback_cache_from_registry(state=self._state)
            return MoveExecutionPlan(
                action_type=ActionType.TX_AUDIT_TRANSCRIPT,  # placeholder; not executed
                action_inputs={"feedback_prompt_id": prompt_id},
                idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, {}),
                hitl_intent_flag=True,
            )

        # mark_resolved_no_edit, mark_blocked, skip_no_action: skip execution.
        return MoveExecutionPlan(
            action_type=ActionType.TX_AUDIT_TRANSCRIPT,  # placeholder; not executed
            action_inputs={},
            idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, {}),
            skip_execution=True,
        )

    # -------------------------------------------------------------------------
    # Hook 7 — supply_progress_metrics
    # -------------------------------------------------------------------------

    def supply_progress_metrics(self, context: OrchestratorContext) -> ProgressMetrics:
        """Phase 7 — Supply progress metric inputs for the shared evaluator."""
        # new_evidence_signal: true if domain signal counter advanced since last iteration.
        new_evidence_signal = self._state.evidence_signal_counter > self._prev_signal_counter

        metrics = ProgressMetrics(
            previous_finding_signature=self._prev_finding_sig,
            current_finding_signature=self._iter_finding_signature,
            previous_blocking_signature=self._prev_blocking_sig,
            current_blocking_signature=self._iter_blocking_signature,
            previous_blocking_count=self._prev_blocking_count,
            current_blocking_count=self._iter_blocking_count,
            new_evidence_signal=new_evidence_signal,
            pending_feedback_prompt_id=self._state.pending_feedback_prompt_id,
            pending_refresh=bool(self._state.pending_reaudit_after_apply),
            refresh_baseline_blocking_count=self._state.apply_reaudit_baseline_blocking_count,
            refresh_baseline_blocking_signature=self._state.apply_reaudit_baseline_blocking_signature,
        )
        # Advance previous-iteration baselines.
        self._prev_finding_sig = self._iter_finding_signature
        self._prev_blocking_sig = self._iter_blocking_signature
        self._prev_blocking_count = self._iter_blocking_count
        self._prev_signal_counter = self._state.evidence_signal_counter
        # Clear pending_reaudit if it was set (kernel will call reset_refresh on ProgressDelta).
        # The actual clearing is done by the kernel via ProgressDelta.reset_refresh.
        return metrics

    # -------------------------------------------------------------------------
    # Hook 8 — supply_closure_rules
    # -------------------------------------------------------------------------

    def supply_closure_rules(self, context: OrchestratorContext) -> ClosureEvaluation:
        """Phase 8 — Evaluate transcript-edit closure conditions.

        Maps transcript-edit terminal conditions to the shared TerminalClass scaffold.
        """
        ledger = self._state.decision_ledger
        iterations = context.loop_memory.iterations
        min_iters = max(
            1,
            min(
                int(self._request.max_iterations),
                int(self._request.min_iterations_before_complete),
            ),
        )
        has_mapping_blocking = has_unresolved_target_scope_mapping_blocking_closure(ledger)
        all_unresolved = _unresolved_closure_requirements(ledger)
        unresolved_count = len(all_unresolved)

        # Not done: still has mapping-blocking items.
        if has_mapping_blocking:
            return ClosureEvaluation(
                domain_complete=False,
                domain_terminal_class="blocked",
                closure_reason_code="mapping_blocking_unresolved",
                open_items_summary=f"{unresolved_count} unresolved items ({len(all_unresolved)} total)",
            )

        # Not done: minimum iterations not yet met.
        if iterations < min_iters:
            return ClosureEvaluation(
                domain_complete=False,
                domain_terminal_class="blocked",
                closure_reason_code="min_iterations_not_met",
                open_items_summary=f"Iteration {iterations} of minimum {min_iters}",
            )

        # TODO (Phase 6b): run image verification pass when needed.
        # handle_clean_iteration's must_verify_before_terminal logic is not yet ported.

        # Evaluate completion policy.
        policy_facts = TranscriptEditFacts(
            iterations=iterations,
            mode=self._request.mode or "audit_then_repair_then_promote",
            auto_promote=bool(self._request.auto_promote),
            error_count=0,
            applied_any_edits=bool(self._state.applied_any_edits),
            applied_non_normalization=bool(self._state.applied_non_normalization),
            applied_requires_review=bool(self._state.applied_requires_review),
            used_human_feedback=bool(self._state.used_human_feedback),
            has_disagreements=unresolved_count > 0,
            has_images=bool(self._request.source_image_refs),
            min_iterations_before_complete=min_iters,
            unresolved_mapping_blocking_closure=has_mapping_blocking,
        )
        should_promote = should_auto_promote_result(policy_facts)
        if should_promote:
            reason = "tx_agent_completed_auto_promote"
        else:
            reason = "tx_agent_completed_needs_review" if unresolved_count > 0 else "tx_agent_completed"
        return ClosureEvaluation(
            domain_complete=True,
            domain_terminal_class="completed",
            closure_reason_code=reason,
            open_items_summary=(
                f"{unresolved_count} optional unresolved items" if unresolved_count > 0 else "all items resolved"
            ),
        )

    # -------------------------------------------------------------------------
    # Hook 9 — integrate_feedback
    # -------------------------------------------------------------------------

    def integrate_feedback(
        self, context: OrchestratorContext, feedback_response: dict[str, Any]
    ) -> IntegrationResult:
        """Pre-phase 2 — Integrate received human feedback into domain work-state.

        The kernel fires this when hitl_state == "answered_unintegrated".
        Domain updates decision_ledger + blocker_registry from the feedback payload.
        Kernel advances HitlState to "consumed" on IntegrationResult.integrated=True.
        Domain must not write HitlState directly.
        """
        if not isinstance(feedback_response, dict):
            return IntegrationResult(integrated=False, integration_summary="invalid_feedback_response")

        self._state.latest_feedback = feedback_response
        # Increment domain signal counter — hook 7 will detect this as new_evidence_signal.
        self._state.evidence_signal_counter += 1
        self._state.used_human_feedback = True
        # NOTE: do NOT reset no_progress_streak here — that is kernel-owned in loop_memory.
        # NOTE: do NOT increment loop_memory.evidence_signal_counter — kernel pre-phase does that.

        feedback_summary = str(feedback_response.get("summary") or "").strip()
        _LOG.info(
            "TX_DOMAIN_PACK integrate_feedback ► request_id=%s summary=%s",
            self._request_id_prefix,
            feedback_summary[:80] if feedback_summary else "(no summary)",
        )
        return IntegrationResult(integrated=True, integration_summary=feedback_summary or "feedback_integrated")

    # -------------------------------------------------------------------------
    # Domain state inspection (for result building)
    # -------------------------------------------------------------------------

    def build_domain_runtime_state(self) -> dict[str, Any]:
        """Build the domain_runtime_state dict for KernelLoopResult.

        Used by the mission-runtime adapter to populate TranscriptEditAgentRunResult.
        """
        state = self._state
        projection = derive_waiting_feedback_projection(
            blocker_registry=state.blocker_registry,
            fallback_prompt_id=state.pending_feedback_prompt_id,
            fallback_decision_key=state.pending_feedback_decision_key,
        )
        mission_runtime_summary = derive_mission_runtime_summary(
            decision_ledger=state.decision_ledger,
            blocker_registry=state.blocker_registry,
            waiting_projection=projection,
        )
        return {
            "used_human_feedback": bool(state.used_human_feedback),
            "feedback_received_count": int(state.feedback_received_count),
            "feedback_consumed_count": int(state.feedback_consumed_count),
            "feedback_stale_count": int(state.feedback_stale_count),
            "feedback_superseded_count": int(state.feedback_superseded_count),
            "mission_runtime_summary": mission_runtime_summary,
            "pending_feedback_prompt_id": projection.get("pending_feedback_prompt_id"),
            "pending_feedback_decision_key": projection.get("pending_feedback_decision_key"),
            "superseded_prompt_ids": sorted(list(state.superseded_feedback_prompt_ids)),
            "hitl_lifecycle_log": list(state.hitl_lifecycle_log),
            "source_completeness": str(state.decision_ledger.get("source_completeness") or "unknown"),
            "convention_context": dict(state.convention_context or {}),
            "blocker_registry": registry_snapshot_for_payload(state.blocker_registry),
            "active_blocker": select_primary_blocker(state.blocker_registry),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prompt_id(focus_key: str, iteration: int) -> str:
    """Deterministic HITL prompt ID from focus key and iteration."""
    raw = f"hitl:{focus_key}:{iteration}"
    return "prompt_" + hashlib.sha1(raw.encode()).hexdigest()[:12]
