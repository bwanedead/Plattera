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
from pathlib import Path
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
from harness.orchestration_kernel.run_progress_frame import build_run_progress_frame

from .blocker_registry import (
    initialize_blocker_registry,
    mark_feedback_received,
    select_primary_blocker,
    sync_registry_from_ledger,
    registry_snapshot_for_payload,
    blocker_health_snapshot,
)
from .contracts import TranscriptEditAgentRunRequest
from .decision_ledger import (
    clear_resolved_after_reaudit,
    initialize_decision_ledger,
    mark_human_resolution_ticket_state,
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
from .evidence_executor import normalize_evidence_request
from .evidence_runtime import (
    run_image_evidence_mode,
    cache_visual_evidence_for_key,
    cache_image_verification_for_key,
)
from .focus_packet import build_focus_packet
from .focus_resolver import resolve_focus_move
from .focus_runtime import recent_image_evidence_attempt_count
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
from .image_verification import final_image_sanity_pass_before_promote
from .result_policy import (
    must_verify_before_terminal,
    should_attempt_promote,
    TranscriptEditFacts,
)
from .state_projection import (
    derive_waiting_feedback_projection,
    sync_pending_feedback_cache_from_registry,
)
from .convention_situating import situate_document_convention
from .blocker_registry import set_convention_context
from .runtime_summary import derive_mission_runtime_summary

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
        identity_trace_cb: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._request = request
        self._session_id = session_id
        self._request_id_prefix = request_id_prefix
        self._mission_objective: str = str(request.mission_objective or "").strip()
        self._identity_trace_cb = identity_trace_cb
        self._planner = planner or TranscriptEditPlanPlanner(
            identity_trace_cb=identity_trace_cb,
        )
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
        # Gate: set True once final_image_sanity_pass_before_promote runs (hook 8 clean path).
        self._image_verification_gate_cleared: bool = False
        # Pending refresh baselines (set when pending_reaudit_after_apply).
        self._refresh_baseline_blocking_count: int | None = None
        self._refresh_baseline_blocking_sig: str | None = None

    def wire_identity_trace_cb(self, cb: Callable[[dict[str, Any]], None] | None) -> None:
        """Inject kernel tracer callback after loop construction (D3 trace observability).

        Called by run_orchestration_kernel_loop after creating KernelTraceCollector,
        so the domain pack and its planner emit llm_call_identity trace events into
        the kernel's persisted trace rather than only debug logs.
        """
        self._identity_trace_cb = cb
        self._planner.wire_identity_trace_cb(cb)

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

        # Seed current_transcript_ref from request on fresh start (before any tool call reads it).
        if not self._state.current_transcript_ref and request.source_transcript_ref:
            self._state.current_transcript_ref = request.source_transcript_ref

        # Initialize domain state if not already restored from resume.
        if not self._state.decision_ledger:
            self._state.decision_ledger = initialize_decision_ledger()
        if not self._state.blocker_registry:
            # P3: if a blocker_registry snapshot was provided for HITL resume, restore it.
            if isinstance(request.resume_blocker_registry, dict) and request.resume_blocker_registry:
                self._state.blocker_registry = dict(request.resume_blocker_registry)
                _LOG.info(
                    "TX_DOMAIN_PACK orient_resume_blocker_registry ► request_id=%s",
                    request_id_prefix,
                )
            else:
                self._state.blocker_registry = initialize_blocker_registry(
                    run_id=request_id_prefix,
                    session_id=session_id,
                    source_transcript_ref=request.source_transcript_ref,
                )

        # P3/F1: restore pending feedback identity fields for HITL resume.
        # Invariant: only set if not already populated (e.g. from initial_state) to
        # ensure resume-restored state is not overwritten by stale request fields.
        resume_prompt_id = str(request.resume_pending_feedback_prompt_id or "").strip() or None
        resume_decision_key = str(request.resume_pending_feedback_decision_key or "").strip().lower() or None
        if resume_prompt_id and not self._state.pending_feedback_prompt_id:
            self._state.pending_feedback_prompt_id = resume_prompt_id
            self._state.pending_feedback_decision_key = resume_decision_key
            _LOG.info(
                "TX_DOMAIN_PACK orient_resume_feedback_identity ► request_id=%s prompt_id=%s",
                request_id_prefix,
                resume_prompt_id,
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

        # D2: seed_transcript_ref is set once at loop start (never overwritten).
        if not self._state.seed_transcript_ref and self._state.current_transcript_ref:
            self._state.seed_transcript_ref = self._state.current_transcript_ref

        # Orient baseline: initializes decision_ledger from source material.
        orient_inputs: dict[str, Any] = {
            "dossier_id": request.dossier_id,
            "model": self._loop_model,
            "run_link_id": request_id_prefix,
            "mission_objective": self._mission_objective,
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

        # D1: discover sibling T0 draft refs when not provided by the caller.
        if not self._state.t0_candidate_refs and not request.candidate_refs and not request.candidate_texts:
            _src = self._state.current_transcript_ref or ""
            if _src:
                _src_path = Path(_src)
                if _src_path.parent.is_dir():
                    _stem = _src_path.stem.split("_v")[0]
                    _siblings = sorted(_src_path.parent.glob(f"{_stem}_v*.json"))
                    self._state.t0_candidate_refs = [str(p) for p in _siblings[:10]]
                    if self._state.t0_candidate_refs:
                        _LOG.info(
                            "TX_DOMAIN_PACK t0_candidates_discovered ► request_id=%s count=%d",
                            request_id_prefix,
                            len(self._state.t0_candidate_refs),
                        )

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

        # Pick up the most recent edited transcript from kernel's latest_refs.
        # After TX_APPLY_EDIT_PLAN executes, the kernel posts tx_edited_transcript_ref
        # into loop_memory.latest_refs.  Without this update, subsequent Phase 2
        # re-audits would keep running against the original source transcript, never
        # seeing the edit's effect, causing refresh_pending_reaudit_grace to fire forever.
        _latest = context.loop_memory.latest_refs or {}
        _edited_ref = (_latest.get("tx_edited_transcript_ref") or {}).get("artifact_path") or ""
        if _edited_ref and _edited_ref != self._state.current_transcript_ref:
            self._state.current_transcript_ref = _edited_ref
            # D2: backfill resulting_ref in the most recent lineage entry that lacks one.
            if self._state.edit_lineage_summary:
                _last = self._state.edit_lineage_summary[-1]
                if isinstance(_last, dict) and not _last.get("resulting_ref"):
                    _last["resulting_ref"] = _edited_ref

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
        # Post-edit re-audit: items absent from new findings are no longer conflicting.
        # update_ledger_from_iteration only accumulates findings; it never clears absent
        # items.  After TX_APPLY_EDIT_PLAN the edited transcript is re-audited here, and
        # if a previously-blocked key (e.g. "range") produces NO finding, the edit fixed
        # it — advance to "verified" so closure logic can proceed.
        if self._state.pending_reaudit_after_apply:
            self._state.decision_ledger = clear_resolved_after_reaudit(
                ledger=self._state.decision_ledger,
                findings=top_findings,
            )
            self._state.pending_reaudit_after_apply = False
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
            seed_transcript_ref=state.seed_transcript_ref,
            edit_lineage_summary=list(state.edit_lineage_summary or []),
            t0_candidate_refs=list(state.t0_candidate_refs or []),
        )
        # D3: inject run-progress frame and rationale-continuity strip into the packet.
        if isinstance(packet, dict):
            packet["run_progress_frame"] = build_run_progress_frame(
                context,
                run_link_id=self._request_id_prefix,
                mission_objective=self._mission_objective or "transcript edit loop",
                domain="transcript_edit",
                surface="tx_planner",
                constitution_version="v1",
            )
            strip = list(getattr(context, "rationale_strip_snapshot", None) or [])
            if strip:
                packet["rationale_continuity_strip"] = strip
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
            validation_mode=str(self._request.validation_mode or "off"),
            run_link_id=self._request_id_prefix,
            mission_objective=self._mission_objective,
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
            # Only capture the baseline on the FIRST edit in a refresh window.
            # If pending_refresh is already True a prior TX_APPLY_EDIT_PLAN already
            # set the baseline from the pre-edit state; overwriting it here would
            # collapse baseline==current and cause an infinite grace loop.
            self._state.pending_reaudit_after_apply = True
            if not context.loop_memory.pending_refresh:
                self._state.apply_reaudit_baseline_blocking_count = self._iter_blocking_count
                self._state.apply_reaudit_baseline_blocking_signature = self._iter_blocking_signature
            self._state.applied_any_edits = True
            # D2: record edit lineage (resulting_ref will be populated in refresh).
            self._state.edit_lineage_summary.append({
                "iteration": iterations,
                "decision_key": focus_key,
                "short_summary": str(payload.get("reason") or "")[:120],
                "resulting_ref": None,
            })
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

            # D3-B: cap image-evidence attempts per focus key at N=2 to prevent oscillation.
            _IMAGE_EVIDENCE_KINDS = {"image_evidence", "image_verify"}
            if evidence_kind in _IMAGE_EVIDENCE_KINDS:
                _recent_img_count = recent_image_evidence_attempt_count(
                    continuity_log=list(self._state.continuity_log or []),
                    decision_key=focus_key,
                )
                if _recent_img_count >= 2:
                    # Exceeded cap — escalate to HITL instead.
                    _LOG.info(
                        "TX_DOMAIN_PACK image_evidence_cap_hit ► request_id=%s focus_key=%s recent=%d",
                        self._request_id_prefix,
                        focus_key,
                        _recent_img_count,
                    )
                    _prompt_id = _make_prompt_id(focus_key, iterations)
                    self._state.pending_feedback_prompt_id = _prompt_id
                    self._state.pending_feedback_decision_key = focus_key
                    self._state.pending_feedback_prompt = {
                        "prompt_id": _prompt_id,
                        "line1": f"Image evidence cap reached for {focus_key!r} ({_recent_img_count} attempts). Human resolution required.",
                        "line2": "Please confirm the correct value for this field.",
                    }
                    return MoveExecutionPlan(
                        action_type=ActionType.TX_AUDIT_TRANSCRIPT,
                        action_inputs={"feedback_prompt_id": _prompt_id},
                        idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, {}),
                        hitl_intent_flag=True,
                    )

            # B — Execute image evidence inline when kind is image_evidence/image_verify.
            if evidence_kind in _IMAGE_EVIDENCE_KINDS:
                normalized_req, norm_reason = normalize_evidence_request(
                    evidence_request=evidence_request,
                    decision_key=focus_key,
                )
                if normalized_req is not None:
                    _req_id = self._request_id_prefix

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
                                idempotency_key=_make_idempotency_key(
                                    f"{_req_id}:{prefix}", iteration, inputs
                                ),
                            )
                        )

                    img_result = run_image_evidence_mode(
                        normalized_request=normalized_req,
                        session_manager=context.session_manager,
                        session_id=context.session_id,
                        iteration=iterations,
                        dossier_id=request.dossier_id,
                        source_transcript_ref=self._state.current_transcript_ref or "",
                        source_image_refs=list(request.source_image_refs or []),
                        model=self._loop_model,
                        focus_decision_key=focus_key,
                        top_findings=self._iter_planning_findings,
                        llm_call_seq_start=self._state.llm_call_seq,
                        progress_cb=self._progress_cb,
                        latest_visual_evidence=self._state.visual_evidence_by_decision_key.get(focus_key),
                        step_fn=_kernel_step_fn,
                        read_step_outputs_inline_fn=read_step_outputs_inline,
                    )
                    _src_hash = self._iter_source_hash
                    _src_ref = self._state.current_transcript_ref
                    if img_result.get("status") == "executed":
                        _visual = img_result.get("image_evidence") or {}
                        if _visual:
                            cache_visual_evidence_for_key(
                                state=self._state,
                                decision_key=focus_key,
                                visual_evidence=_visual,
                                source_transcript_ref=_src_ref,
                                source_transcript_hash=_src_hash,
                            )
                            self._state.evidence_signal_counter += 1
                        _img_verify = img_result.get("image_verification") or {}
                        if _img_verify:
                            cache_image_verification_for_key(
                                state=self._state,
                                decision_key=focus_key,
                                image_verification=_img_verify,
                                source_transcript_ref=_src_ref,
                                source_transcript_hash=_src_hash,
                            )
                        if isinstance(img_result.get("latest_refs"), dict):
                            self._state.latest_refs = img_result["latest_refs"]
                        self._state.llm_call_seq = int(
                            img_result.get("llm_call_seq_end") or self._state.llm_call_seq
                        )
                    _LOG.info(
                        "TX_DOMAIN_PACK image_evidence_executed ► request_id=%s focus_key=%s status=%s",
                        self._request_id_prefix,
                        focus_key,
                        img_result.get("status"),
                    )
                    return MoveExecutionPlan(
                        action_type=ActionType.TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
                        action_inputs={},
                        idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, {}),
                        skip_execution=True,
                    )
                else:
                    _LOG.warning(
                        "TX_DOMAIN_PACK image_evidence_norm_fail ► request_id=%s focus_key=%s reason=%s",
                        self._request_id_prefix,
                        focus_key,
                        norm_reason,
                    )
                    # Fall through to default audit on normalization failure.

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
            # Do NOT call sync_pending_feedback_cache_from_registry here — when the registry
            # has rows but none in waiting_feedback state, the sync would clear the prompt_id
            # we just set (projection ignores fallback when has_registry_rows=True).
            self._state.pending_feedback_prompt_id = prompt_id
            self._state.pending_feedback_decision_key = focus_key
            self._state.pending_feedback_prompt = dict(feedback_prompt)
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
            # Use kernel-owned pending_refresh flag (D3: kernel is the authoritative trigger).
            pending_refresh=context.loop_memory.pending_refresh,
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

        # D2 (Phase 8): image-verification clean-path gate.
        # must_verify_before_terminal mirrors handle_clean_iteration's terminal gate.
        # Run the final sanity pass inline once; if it fails, gate completion.
        if must_verify_before_terminal(policy_facts) and not self._image_verification_gate_cleared:
            transcript_ref = self._state.current_transcript_ref
            if transcript_ref:
                session_manager = context.session_manager
                session_id = context.session_id

                def _step_fn(
                    *,
                    session_manager: Any = session_manager,
                    session_id: str = session_id,
                    prefix: str,
                    iteration: int,
                    action_type: Any,
                    inputs: dict[str, Any],
                ) -> Any:
                    from agent_kernel.models import KernelStepRequest as _KSR
                    return session_manager.step(
                        _KSR(
                            session_id=session_id,
                            action_type=action_type,
                            inputs=inputs,
                            idempotency_key=_make_idempotency_key(
                                f"{prefix}:{iteration}", iteration, inputs
                            ),
                        )
                    )

                final_verify = final_image_sanity_pass_before_promote(
                    session_manager=session_manager,
                    session_id=session_id,
                    iteration=iterations,
                    dossier_id=self._request.dossier_id,
                    source_transcript_ref=transcript_ref,
                    source_image_refs=list(self._request.source_image_refs or []),
                    disagreement_hints={},
                    model=self._loop_model,
                    step_fn=_step_fn,
                    read_step_outputs_inline_fn=read_step_outputs_inline,
                    read_str_fn=read_str,
                    read_int_fn=read_int,
                )
                self._state.latest_refs = final_verify.get("latest_refs", self._state.latest_refs)
                self._image_verification_gate_cleared = True

                if not bool(final_verify.get("passed")):
                    verify_reason = read_str(final_verify.get("reason")) or "tx_final_image_verify_failed"
                    _LOG.warning(
                        "TX_DOMAIN_PACK supply_closure_rules_image_verify_failed ► iter=%s reason=%s",
                        iterations,
                        verify_reason,
                    )
                    # If more iterations remain, gate completion and let the kernel retry.
                    if iterations < int(self._request.max_iterations):
                        return ClosureEvaluation(
                            domain_complete=False,
                            domain_terminal_class="blocked",
                            closure_reason_code="image_verification_retry_required",
                            open_items_summary=f"verify_failed:{verify_reason}",
                        )
                    # At max iterations: surface as needs-review terminal.
                    return ClosureEvaluation(
                        domain_complete=True,
                        domain_terminal_class="completed",
                        closure_reason_code="tx_agent_completed_needs_review",
                        open_items_summary=f"image_verify_failed_at_max_iter:{verify_reason}",
                    )
        should_promote = should_attempt_promote(policy_facts, "audit_then_repair_then_promote")
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

        decision_key = str(
            feedback_response.get("decision_key") or self._state.pending_feedback_decision_key or ""
        ).strip().lower()
        prompt_id = str(
            feedback_response.get("prompt_id") or self._state.pending_feedback_prompt_id or ""
        ).strip() or None
        feedback_value = str(feedback_response.get("selected_value") or "").strip() or None
        feedback_note = str(feedback_response.get("note") or "").strip() or None

        # Update blocker registry — marks the blocker as having received feedback.
        if decision_key:
            self._state.blocker_registry = mark_feedback_received(
                registry=self._state.blocker_registry,
                decision_key=decision_key,
                prompt_id=prompt_id or "",
                feedback_value=feedback_value,
                feedback_note=feedback_note,
                reason="hook9_feedback_integration",
            )

        # Update decision ledger — marks the ticket as integrated.
        if prompt_id and decision_key:
            self._state.decision_ledger = mark_human_resolution_ticket_state(
                ledger=self._state.decision_ledger,
                ticket_id=prompt_id,
                decision_key=decision_key,
                lifecycle_state="integrated",
                relevance="active",
            )

        self._state.latest_feedback = feedback_response
        # Increment domain signal counter — hook 7 will detect this as new_evidence_signal.
        self._state.evidence_signal_counter += 1
        self._state.used_human_feedback = True
        # Clear pending feedback state.
        self._state.pending_feedback_prompt_id = None
        self._state.pending_feedback_decision_key = None
        sync_pending_feedback_cache_from_registry(state=self._state)
        # NOTE: do NOT reset no_progress_streak here — that is kernel-owned in loop_memory.
        # NOTE: do NOT increment loop_memory.evidence_signal_counter — kernel pre-phase does that.

        feedback_summary = str(feedback_response.get("summary") or "").strip()
        _LOG.info(
            "TX_DOMAIN_PACK integrate_feedback ► request_id=%s decision_key=%s summary=%s",
            self._request_id_prefix,
            decision_key or "(none)",
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
            "pending_feedback_prompt": dict(state.pending_feedback_prompt) if isinstance(state.pending_feedback_prompt, dict) else None,
            # Expose state-level prompt fields directly — the projection may not surface
            # these when the blocker_registry has rows but no row is in waiting_feedback state.
            "state_pending_feedback_prompt_id": str(state.pending_feedback_prompt_id or "").strip() or None,
            "state_pending_feedback_decision_key": str(state.pending_feedback_decision_key or "").strip().lower() or None,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prompt_id(focus_key: str, iteration: int) -> str:
    """Deterministic HITL prompt ID from focus key and iteration."""
    raw = f"hitl:{focus_key}:{iteration}"
    return "prompt_" + hashlib.sha1(raw.encode()).hexdigest()[:12]
