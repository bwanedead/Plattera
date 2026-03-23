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
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from agent_kernel.models import KernelStepRequest, StepExecutionState

from .execution_action_ids import (
    TX_APPLY_EDIT_PLAN,
    TX_AUDIT_TRANSCRIPT,
    TX_OPEN_TRANSCRIPT_SPANS,
    TX_ORIENT_AND_BASELINE,
    TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
)
from agents.common.identity_composer import CONSTITUTION_VERSION
from config.paths import agent_kernel_artifacts_root

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
from .decision_ledger_adapter import transcript_edit_unified_and_closure_read_from_loop_state
from .llm_startup_understanding import (
    apply_llm_startup_to_ledger_and_registry,
    fallback_decision_key_for_startup_merge,
)
from .decision_ledger_focus import choose_investigation_focus
from .domain_pack_focus_wiring import choose_investigation_fallback_focus_from_state
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
        # Apply compile → execute: optimistic lineage/baselines only after confirmed edited artifact.
        self._awaiting_apply_outcome: bool = False
        self._pre_apply_blocking_count: int = 0
        self._pre_apply_blocking_signature: str = ""
        self._pending_lineage_meta: dict[str, Any] | None = None
        self._orient_baseline_failure_reason: str | None = None
        # Phase 22: force audit/orient inputs to use this path when tools echo a different tx_source ref.
        self._working_transcript_override: str | None = None

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
        """Phase 1 — LLM orient baseline + initial domain state setup (Phase 23).

        Runs TX_ORIENT_AND_BASELINE first — startup understanding and baseline items are LLM-authored.
        Deterministic transcript audit is not used to author initial ledger rows or startup meaning here.
        Initializes decision_ledger, blocker_registry, convention_context.
        Also handles resume state restoration when initial_state was provided.
        """
        request = self._request
        session_manager = context.session_manager
        session_id = context.session_id
        request_id_prefix = context.request_id_prefix

        # Phase 22 — Working transcript authority (explicit precedence):
        # 1) resume_working_transcript_ref (latest successful edited artifact from prior run/session)
        # 2) source_transcript_ref / source_text (original import or dossier canonical source)
        _rw = str(getattr(request, "resume_working_transcript_ref", None) or "").strip()
        _src = str(request.source_transcript_ref or "").strip()
        _oseed = str(getattr(request, "original_seed_transcript_ref", None) or "").strip()
        if _rw:
            self._state.current_transcript_ref = _rw
            _LOG.info(
                "TX_DOMAIN_PACK working_transcript ► request_id=%s ref=resume_working path=%s",
                request_id_prefix,
                _rw[:120],
            )
        elif _src:
            self._state.current_transcript_ref = _src
        elif not self._state.current_transcript_ref and request.source_text:
            pass  # source_text handled below for audit inputs only

        self._working_transcript_override = _rw or None

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
                _reg_src = _oseed or _src or str(self._state.current_transcript_ref or "").strip()
                self._state.blocker_registry = initialize_blocker_registry(
                    run_id=request_id_prefix,
                    session_id=session_id,
                    source_transcript_ref=_reg_src or request.source_transcript_ref,
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

        # Phase 23: no pre-audit at startup — source hash/ref come from orient outputs (or resume paths above).
        self._pre_source_hash = ""

        # D2: seed_transcript_ref is set once at loop start (never overwritten).
        if not self._state.seed_transcript_ref:
            if _oseed:
                self._state.seed_transcript_ref = _oseed
            elif _rw and _src:
                self._state.seed_transcript_ref = _src
            elif self._state.current_transcript_ref:
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
                action_type=TX_ORIENT_AND_BASELINE,
                inputs=orient_inputs,
                idempotency_key=_make_idempotency_key(
                    f"{request_id_prefix}:orient", 0, orient_inputs
                ),
            )
        )
        self._orient_baseline_failure_reason = None
        if orient.execution_state != StepExecutionState.EXECUTED:
            _inline = read_step_outputs_inline(orient.step_record) if orient.step_record else {}
            _kr = _inline.get("kernel_refusal") if isinstance(_inline.get("kernel_refusal"), dict) else {}
            _rc = str(_kr.get("reason_code") or "").strip()
            if not _rc and orient.refusal is not None:
                _rc = str(orient.refusal.reason_code or "").strip()
            self._orient_baseline_failure_reason = _rc or "tx_orient_baseline_step_refused"
            _LOG.warning(
                "TX_DOMAIN_PACK orient_refused ► request_id=%s reason=%s",
                request_id_prefix,
                self._orient_baseline_failure_reason,
            )
        if orient.execution_state == StepExecutionState.EXECUTED and orient.dashboard:
            self._state.latest_refs = orient.dashboard.latest_refs.model_dump(mode="json")
            orient_inline = read_step_outputs_inline(orient.step_record)
            orient_src_ref = read_str(orient_inline.get("tx_source_transcript_ref"))
            if self._working_transcript_override:
                self._state.current_transcript_ref = self._working_transcript_override
            elif orient_src_ref:
                self._state.current_transcript_ref = orient_src_ref
            self._pre_source_hash = read_str(orient_inline.get("tx_source_transcript_hash")) or ""
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
            startup_raw = orient_inline.get("tx_startup_understanding")
            if not isinstance(startup_raw, dict):
                startup_raw = {}
            _fb_key = fallback_decision_key_for_startup_merge(
                orient_items=orient_items,
                startup=startup_raw,
            )
            _merge_stats: dict[str, Any] = {}
            self._state.decision_ledger, self._state.blocker_registry = apply_llm_startup_to_ledger_and_registry(
                ledger=self._state.decision_ledger,
                registry=self._state.blocker_registry,
                startup=startup_raw,
                merge_stats=_merge_stats,
                fallback_decision_key=_fb_key,
            )
            self._state.llm_startup_understanding = (
                dict(self._state.decision_ledger.get("llm_startup_understanding"))
                if isinstance(self._state.decision_ledger.get("llm_startup_understanding"), dict)
                else None
            )
            self._state.convention_context = situate_document_convention(orient_items=orient_items)
            self._state.blocker_registry = set_convention_context(
                registry=self._state.blocker_registry,
                convention_context=self._state.convention_context,
            )
            # D1: count actual orient LLM contacts (may be >1 on retries).
            _orient_llm_contacts = max(1, int(orient_inline.get("tx_orient_llm_contacts") or 1))
            for _ in range(_orient_llm_contacts):
                context.loop_memory.register_llm_contact()

        # Sync blocker registry from closure read model (aligned with unified envelope).
        _, read_after_orient = transcript_edit_unified_and_closure_read_from_loop_state(self._state)
        self._state.blocker_registry = sync_registry_from_ledger(
            registry=self._state.blocker_registry,
            decision_ledger=read_after_orient,
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

        # D2: generate investigation summary once after orient completes.
        if not self._state.investigation_summary_ref:
            self._state.investigation_summary_ref = self._generate_investigation_summary(
                request_id_prefix=request_id_prefix,
                dossier_id=request.dossier_id or "unknown",
                llm_contact_at_generation=context.loop_memory.llm_contact_count,
            )
            # Initial scene survey is materially complete once orient + summary exist.
            if self._state.investigation_summary_ref:
                self._state.initial_recon_complete = True
                # Surface in latest_refs so it appears in CLI output and loop result.
                self._state.latest_refs["tx_investigation_summary_ref"] = {
                    "path": self._state.investigation_summary_ref
                }

        _, _orient_read = transcript_edit_unified_and_closure_read_from_loop_state(self._state)
        _items = _orient_read.get("items") or []
        _ledger_item_count = len(_items) if isinstance(_items, list) else 0
        _LOG.info(
            "TX_DOMAIN_PACK orient_complete ► request_id=%s ledger_keys=%s",
            request_id_prefix,
            _ledger_item_count,
        )

    # -------------------------------------------------------------------------
    # D2 — Investigation summary helper (generated once after orient)
    # -------------------------------------------------------------------------

    def _generate_investigation_summary(
        self,
        *,
        request_id_prefix: str,
        dossier_id: str,
        llm_contact_at_generation: int,
    ) -> str | None:
        """Persist a bounded scene-map artifact once after orient completes.

        The summary captures what we know at orient time (transcript refs, t0 siblings,
        top discrepancies, available evidence lanes) so subsequent iterations can
        anchor to it instead of re-surveying from scratch.

        Returns the artifact file path string, or None on failure.
        """
        try:
            state = self._state
            _, read_ledger = transcript_edit_unified_and_closure_read_from_loop_state(state)
            items_list = read_ledger.get("items") or []
            if not isinstance(items_list, list):
                items_list = []

            # Top discrepancies: mapping-blocking items first, max 5.
            top_discrepancies: list[dict[str, Any]] = []
            for item in items_list:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key") or "").strip().lower()
                top_discrepancies.append({
                    "key": key,
                    "verdict": item.get("verdict"),
                    "mapping_blocking": item.get("mapping_blocking", False),
                    "state": item.get("state"),
                })
            top_discrepancies.sort(key=lambda x: (not x.get("mapping_blocking", False), x.get("key", "")))
            top_discrepancies = top_discrepancies[:5]

            summary = {
                "artifact_kind": "tx_investigation_summary",
                "schema_version": "v1",
                "run_id": request_id_prefix,
                "generated_at_llm_contact": llm_contact_at_generation,
                "initial_recon_complete": True,
                "source_transcript_ref": state.current_transcript_ref,
                "seed_transcript_ref": state.seed_transcript_ref,
                "t0_candidate_refs": list(state.t0_candidate_refs or []),
                "t0_candidate_count": len(state.t0_candidate_refs or []),
                "working_draft_selection_basis": "heuristic_v2_seed",
                "top_discrepancies": top_discrepancies,
                "evidence_lanes_available": ["span", "image", "hitl"],
                "coverage": {
                    "orient_baseline_complete": True,
                    "image_evidence_attempted": False,
                    "span_evidence_attempted": False,
                    "hitl_received": False,
                },
            }

            root = (
                agent_kernel_artifacts_root()
                / "tool_outputs"
                / "tx_investigation_summary"
                / dossier_id
            )
            root.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            artifact_name = f"investigation_summary_{ts}_{uuid4().hex[:8]}.json"
            path = root / artifact_name

            fd, tmp_path = tempfile.mkstemp(prefix="inv_summary_", suffix=".json", dir=str(root))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(summary, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                try:
                    os.replace(tmp_path, str(path))
                except PermissionError:
                    with path.open("w", encoding="utf-8") as f:
                        json.dump(summary, f, ensure_ascii=False, indent=2)
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

            _LOG.info(
                "TX_DOMAIN_PACK investigation_summary_persisted ► request_id=%s path=%s",
                request_id_prefix,
                path,
            )
            return str(path)
        except Exception:
            _LOG.exception(
                "TX_DOMAIN_PACK investigation_summary_failed ► request_id=%s", request_id_prefix
            )
            return None

    def _load_investigation_excerpt(self) -> dict[str, Any] | None:
        """Load a bounded model-facing excerpt from the persisted investigation summary.

        Returns a compact dict with the fields most useful for model reasoning, or None
        if the summary ref is unset or the file cannot be read.
        """
        ref = self._state.investigation_summary_ref
        if not ref:
            return None
        try:
            with open(ref, encoding="utf-8") as f:
                data = json.load(f)
            return {
                "working_draft_basis": data.get("working_draft_selection_basis"),
                "source_transcript_ref": data.get("source_transcript_ref"),
                "t0_candidate_count": data.get("t0_candidate_count", 0),
                "top_discrepancies": data.get("top_discrepancies") or [],
                "evidence_lanes_available": data.get("evidence_lanes_available") or [],
                "coverage": data.get("coverage") or {},
            }
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Hook 2 — refresh
    # -------------------------------------------------------------------------

    def refresh(self, context: OrchestratorContext) -> RefreshResult:
        """Phase 2 — Per-iteration audit + ledger update.

        Runs TX_AUDIT_TRANSCRIPT for mechanical tracing and refs. Inspection observations are
        evidence-only: they merge source-completeness signals only; ledger and discovery meaning
        stay LLM-authored (startup and iteration updates).
        """
        request = self._request
        session_manager = context.session_manager
        session_id = context.session_id
        iterations = context.loop_memory.iterations

        # If the previous kernel step was a refused TX_APPLY, drop optimistic apply-compile state
        # so we do not run clear_resolved_after_reaudit or grant false progress baselines.
        _step_ref = context.loop_memory.last_step_refusal_record
        if isinstance(_step_ref, dict):
            _action = str(_step_ref.get("action") or "")
            _inline_sr = _step_ref.get("outputs_inline") if isinstance(_step_ref.get("outputs_inline"), dict) else {}
            _kr_sr = _inline_sr.get("kernel_refusal") if isinstance(_inline_sr.get("kernel_refusal"), dict) else {}
            _rc_sr = str(_kr_sr.get("reason_code") or "").strip()
            if _action == "tx_apply_edit_plan" or "tx_apply_refused" in _rc_sr:
                self._awaiting_apply_outcome = False
                self._pending_lineage_meta = None
                self._state.apply_reaudit_baseline_blocking_count = None
                self._state.apply_reaudit_baseline_blocking_signature = None

        # Pick up the most recent edited transcript from kernel's latest_refs.
        # After TX_APPLY_EDIT_PLAN executes, the kernel posts tx_edited_transcript_ref
        # into loop_memory.latest_refs.  Without this update, subsequent Phase 2
        # re-audits would keep running against the original source transcript, never
        # seeing the edit's effect, causing refresh_pending_reaudit_grace to fire forever.
        _latest = context.loop_memory.latest_refs or {}
        _edited_ref = (_latest.get("tx_edited_transcript_ref") or {}).get("artifact_path") or ""
        if _edited_ref and _edited_ref != self._state.current_transcript_ref:
            if self._awaiting_apply_outcome:
                self._state.pending_reaudit_after_apply = True
                self._awaiting_apply_outcome = False
                self._state.applied_any_edits = True
                _meta = self._pending_lineage_meta
                self._pending_lineage_meta = None
                if isinstance(_meta, dict):
                    self._state.edit_lineage_summary.append(
                        {
                            "iteration": _meta.get("iteration"),
                            "decision_key": _meta.get("focus_key"),
                            "short_summary": _meta.get("summary"),
                            "resulting_ref": _edited_ref,
                        }
                    )
            self._state.current_transcript_ref = _edited_ref
            self._working_transcript_override = _edited_ref
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
                action_type=TX_AUDIT_TRANSCRIPT,
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
        if self._working_transcript_override:
            self._state.current_transcript_ref = self._working_transcript_override
        elif src_ref:
            self._state.current_transcript_ref = src_ref

        findings_summary = (
            inline.get("tx_validator_summary")
            if isinstance(inline.get("tx_validator_summary"), dict)
            else {}
        )
        _ev_obs = inline.get("tx_evidence_observations")
        top_findings = (
            _ev_obs
            if isinstance(_ev_obs, list)
            else (
                inline.get("tx_top_findings")
                if isinstance(inline.get("tx_top_findings"), list)
                else []
            )
        )
        src_hash = (
            read_str(inline.get("tx_source_transcript_hash"))
            or getattr(self, "_pre_source_hash", "")
        )

        # Audit/inspection output is evidence only — mechanical source-completeness merge, no ledger/discovery authorship.
        self._state.last_audit_evidence_snapshot = {
            "schema_version": "audit_evidence_snapshot.v1",
            "iteration": int(context.loop_memory.iterations),
            "validator_summary": dict(findings_summary) if isinstance(findings_summary, dict) else {},
            "observations": [dict(x) for x in top_findings if isinstance(x, dict)][:24],
            "source_transcript_hash": src_hash,
        }
        self._state.decision_ledger = update_ledger_from_iteration(
            ledger=self._state.decision_ledger,
            findings=[dict(x) for x in top_findings if isinstance(x, dict)],
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
        _, read_after_refresh = transcript_edit_unified_and_closure_read_from_loop_state(self._state)
        self._state.blocker_registry = sync_registry_from_ledger(
            registry=self._state.blocker_registry,
            decision_ledger=read_after_refresh,
            run_id=self._request_id_prefix,
            session_id=session_id,
            source_transcript_ref=self._state.current_transcript_ref,
        )
        sync_pending_feedback_cache_from_registry(state=self._state)

        # Derive and cache per-iteration signatures for hook 7.
        self._iter_finding_signature = finding_signature(
            summary=findings_summary, findings=top_findings
        )
        self._iter_blocking_signature = blocking_signature(read_after_refresh)
        self._iter_blocking_count = blocking_unresolved_count(read_after_refresh)
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
        state = self._state
        unified, read_ledger = transcript_edit_unified_and_closure_read_from_loop_state(state)
        registry = state.blocker_registry

        # Work-item collection: mapping-blocking unresolved items (closure read model).
        unresolved = unresolved_mapping_blocking_requirements(read_ledger)
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
        all_unresolved = _unresolved_closure_requirements(read_ledger)
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
            fallback_focus = choose_investigation_focus(state.decision_ledger, work_board=unified) or {}
            feedback_payload = (
                dict(self._state.latest_feedback)
                if isinstance(self._state.latest_feedback, dict)
                else None
            )
            focus_target = _select_focus_target(
                decision_ledger=read_ledger,
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

        _, read_ledger = transcript_edit_unified_and_closure_read_from_loop_state(state)
        fallback_focus = choose_investigation_fallback_focus_from_state(state)
        focus_target = _select_focus_target(
            decision_ledger=read_ledger,
            fallback_focus=fallback_focus,
            focus_feedback=feedback,
            blocker_registry=state.blocker_registry,
        )
        target_key = str((focus_target or {}).get("decision_key") or "").strip().lower()
        aligned_with_kernel = target_key == str(focus_key or "").strip().lower()
        focus_source = str((focus_target or {}).get("focus_source") or "legacy_fallback").strip().lower() or "legacy_fallback"
        focus_reason_code = str((focus_target or {}).get("focus_reason_code") or "domain_pack_focus").strip()[:120] or "domain_pack_focus"
        emergent_from_target = None
        if aligned_with_kernel and isinstance((focus_target or {}).get("active_blocker"), dict):
            emergent_from_target = dict((focus_target or {})["active_blocker"])

        # Native store only — ``build_focus_packet`` builds unified + closure read models inside.
        packet = build_focus_packet(
            decision_ledger=state.decision_ledger,
            decision_key=focus_key,
            focus_source=focus_source,
            focus_reason_code=focus_reason_code,
            loop_iteration=context.loop_memory.iterations,
            active_emergent_blocker=emergent_from_target or active_blocker,
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
            evidence_repeat_guard=state.evidence_repeat_guard,
            evidence_signal_counter=state.evidence_signal_counter,
            harness_emergent_board_items=list(state.harness_emergent_board_items or []),
            harness_board_context_notes=dict(state.harness_board_context_notes or {}),
            audit_evidence_snapshot=(
                dict(state.last_audit_evidence_snapshot)
                if isinstance(state.last_audit_evidence_snapshot, dict)
                else None
            ),
        )
        # D3: inject run-progress frame and rationale-continuity strip into the packet.
        # D2: inject investigation summary ref + state for cumulative grounding.
        if isinstance(packet, dict):
            packet["run_progress_frame"] = build_run_progress_frame(
                context,
                run_link_id=self._request_id_prefix,
                mission_objective=self._mission_objective or "transcript edit loop",
                domain="transcript_edit",
                constitution_version=CONSTITUTION_VERSION,
            )
            strip = list(getattr(context, "rationale_strip_snapshot", None) or [])
            if strip:
                packet["rationale_continuity_strip"] = strip
            # D2: investigation summary — present from orient onward; tells the LLM
            # what reconnaissance has already been done so it doesn't re-survey.
            # Inject both the ref (for durable access) and a bounded excerpt
            # (for direct model reasoning without artifact round-trip).
            _inv_excerpt = self._load_investigation_excerpt()
            packet["investigation_state"] = {
                "ref": self._state.investigation_summary_ref,
                "initial_recon_complete": self._state.initial_recon_complete,
                "excerpt": _inv_excerpt,
            }
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
        # Scoped to this orchestration invocation (``_request_id_prefix``); new prefix ⇒ fresh idempotency space.
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
            # Baselines for hook-7 progress (post-apply grace) — captured from pre-execute audit state.
            # pending_reaudit_after_apply and lineage are set only after refresh confirms a new edited artifact.
            self._pre_apply_blocking_count = self._iter_blocking_count
            self._pre_apply_blocking_signature = self._iter_blocking_signature
            self._awaiting_apply_outcome = True
            self._pending_lineage_meta = {
                "iteration": iterations,
                "focus_key": focus_key,
                "summary": str(payload.get("reason") or "")[:120],
            }
            if not context.loop_memory.pending_refresh:
                self._state.apply_reaudit_baseline_blocking_count = self._iter_blocking_count
                self._state.apply_reaudit_baseline_blocking_signature = self._iter_blocking_signature
            return MoveExecutionPlan(
                action_type=TX_APPLY_EDIT_PLAN,
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
                        action_type=TX_AUDIT_TRANSCRIPT,
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
                        _seq_before = self._state.llm_call_seq
                        self._state.llm_call_seq = int(
                            img_result.get("llm_call_seq_end") or _seq_before
                        )
                        # D4: count image locator/verifier LLM contacts via seq delta.
                        _img_llm_contacts = max(0, self._state.llm_call_seq - _seq_before)
                        for _ in range(_img_llm_contacts):
                            context.loop_memory.register_llm_contact()
                    _LOG.info(
                        "TX_DOMAIN_PACK image_evidence_executed ► request_id=%s focus_key=%s status=%s",
                        self._request_id_prefix,
                        focus_key,
                        img_result.get("status"),
                    )
                    return MoveExecutionPlan(
                        action_type=TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
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
                    action_type=TX_OPEN_TRANSCRIPT_SPANS,
                    action_inputs=inputs,
                    idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, inputs),
                )
            # Default: re-audit as a fallback investigation step.
            inputs = {"dossier_id": request.dossier_id}
            if self._state.current_transcript_ref:
                inputs["source_transcript_ref"] = self._state.current_transcript_ref
            return MoveExecutionPlan(
                action_type=TX_AUDIT_TRANSCRIPT,
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
                action_type=TX_AUDIT_TRANSCRIPT,  # placeholder; not executed
                action_inputs={"feedback_prompt_id": prompt_id},
                idempotency_key=_make_idempotency_key(idempotency_prefix, iterations, {}),
                hitl_intent_flag=True,
            )

        # mark_resolved_no_edit, mark_blocked, skip_no_action: skip execution.
        return MoveExecutionPlan(
            action_type=TX_AUDIT_TRANSCRIPT,  # placeholder; not executed
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
        _, read_ledger = transcript_edit_unified_and_closure_read_from_loop_state(self._state)
        iterations = context.loop_memory.iterations
        min_iters = max(
            1,
            min(
                int(self._request.max_iterations),
                int(self._request.min_iterations_before_complete),
            ),
        )
        has_mapping_blocking = has_unresolved_target_scope_mapping_blocking_closure(read_ledger)
        all_unresolved = _unresolved_closure_requirements(read_ledger)
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
        _, read_ledger = transcript_edit_unified_and_closure_read_from_loop_state(state)
        projection = derive_waiting_feedback_projection(
            blocker_registry=state.blocker_registry,
            fallback_prompt_id=state.pending_feedback_prompt_id,
            fallback_decision_key=state.pending_feedback_decision_key,
        )
        mission_runtime_summary = derive_mission_runtime_summary(
            decision_ledger=read_ledger,
            blocker_registry=state.blocker_registry,
            waiting_projection=projection,
        )
        return {
            "working_transcript_ref": state.current_transcript_ref,
            "seed_transcript_ref": state.seed_transcript_ref,
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
            "source_completeness": str(read_ledger.get("source_completeness") or "unknown"),
            "convention_context": dict(state.convention_context or {}),
            "blocker_registry": registry_snapshot_for_payload(state.blocker_registry),
            "active_blocker": select_primary_blocker(state.blocker_registry),
            "pending_feedback_prompt": dict(state.pending_feedback_prompt) if isinstance(state.pending_feedback_prompt, dict) else None,
            # Expose state-level prompt fields directly — the projection may not surface
            # these when the blocker_registry has rows but no row is in waiting_feedback state.
            "state_pending_feedback_prompt_id": str(state.pending_feedback_prompt_id or "").strip() or None,
            "state_pending_feedback_decision_key": str(state.pending_feedback_decision_key or "").strip().lower() or None,
            "orient_baseline_failure_reason": self._orient_baseline_failure_reason,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prompt_id(focus_key: str, iteration: int) -> str:
    """Deterministic HITL prompt ID from focus key and iteration."""
    raw = f"hitl:{focus_key}:{iteration}"
    return "prompt_" + hashlib.sha1(raw.encode()).hexdigest()[:12]
