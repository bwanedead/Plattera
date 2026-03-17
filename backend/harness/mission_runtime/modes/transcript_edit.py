from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from agent_kernel.models import KernelBudgets, KernelGoal, KernelSessionStartRequest
from agent_kernel.session import KernelSessionManager
from agents.transcript_edit.contracts import TranscriptEditAgentRunRequest, TranscriptEditAgentRunResult
from agents.transcript_edit.domain_pack import TranscriptEditDomainPack
from harness.orchestration_kernel import KernelLoopResult, run_orchestration_kernel_loop
from harness.tracing.kernel_trace_persistence import persist_kernel_trace

from ...terminal_taxonomy import classify_transcript_edit_terminal
from ..contracts import (
    MissionBlockerPostureSummary,
    MissionLedgerView,
    MissionResumabilitySummary,
    MissionRuntimeRequest,
    MissionVerificationPostureSummary,
    ModeCycleContext,
    ModeInterpretation,
    ModePolicy,
    ModeRecommendation,
    ModeTransitionRecommendation,
    TerminalRecommendation,
)

TRANSCRIPT_EDIT_MODE_NAME = "transcript_edit"


@dataclass(frozen=True)
class _TranscriptAuthoritySnapshot:
    waiting_feedback: bool
    pending_feedback_prompt_id: str | None
    open_blocker_count: int | None
    unresolved_closure_count: int
    closure_blocking: bool
    verification_status: str
    verification_kind: str
    terminal_classification: str | None


class TranscriptEditModePolicy(ModePolicy):
    mode_name = TRANSCRIPT_EDIT_MODE_NAME

    def __init__(
        self,
        *,
        runner: Callable[[MissionRuntimeRequest, MissionLedgerView], TranscriptEditAgentRunResult],
    ) -> None:
        self._runner = runner

    def build_context(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
    ) -> ModeCycleContext:
        return ModeCycleContext(
            payload={},
            execution_adapter=lambda: self._runner(request, ledger),
        )

    def interpret(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
    ) -> ModeInterpretation:
        return interpret_transcript_edit_run_result(_require_transcript_result(context))

    def recommend(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
        interpretation: ModeInterpretation,
    ) -> ModeRecommendation:
        result = _require_transcript_result(context)
        recommendation = recommend_transcript_edit_run_result(result)
        transition = _recommend_transition_back_to_deed_to_ir(
            request=request,
            recommendation=recommendation,
            result=result,
        )
        if transition is None:
            return recommendation
        return ModeRecommendation(
            next_step_hint="handoff_back_to_deed_to_ir",
            transition=transition,
            terminal=recommendation.terminal,
            high_signal_artifact_refs=list(recommendation.high_signal_artifact_refs),
            blocker_posture=recommendation.blocker_posture,
            verification_posture=recommendation.verification_posture,
            resumability=recommendation.resumability,
        )


def build_transcript_edit_mode_policy_from_controller_inputs(
    *,
    session_manager: KernelSessionManager,
    transcript_request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    planner: Any | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> TranscriptEditModePolicy:
    def _runner(
        _request: MissionRuntimeRequest,
        _ledger: MissionLedgerView,
    ) -> TranscriptEditAgentRunResult:
        return run_orchestration_kernel_transcript_loop(
            session_manager=session_manager,
            request=transcript_request,
            request_id_prefix=request_id_prefix,
            planner=planner,
            progress_cb=progress_cb,
        )

    return TranscriptEditModePolicy(runner=_runner)


# ---------------------------------------------------------------------------
# Orchestration kernel runner + adapter
# ---------------------------------------------------------------------------


def run_orchestration_kernel_transcript_loop(
    *,
    session_manager: KernelSessionManager,
    request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    planner: Any | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    resume_feedback_response: dict[str, Any] | None = None,
) -> TranscriptEditAgentRunResult:
    """Run transcript-edit through the orchestration kernel and adapt the result.

    ``resume_feedback_response`` — when provided, the kernel HITL state machine is
    pre-seeded as "answered_unintegrated" so the first iteration's pre-phase fires
    ``integrate_feedback`` with this payload.  Used by the CLI HITL resume loop (P3).
    """
    # Start a kernel session so the domain pack can call session_manager.step().
    max_steps = max(8, int(request.max_iterations) * 4)
    start_request = KernelSessionStartRequest(
        request_id=f"{request_id_prefix}-ok",
        goal=KernelGoal(
            requires_global_placement=False,
            render_required=False,
            objective="orchestration_kernel_transcript_edit",
        ),
        budgets=KernelBudgets(
            max_steps=max_steps,
            max_wall_time_seconds=600,
            max_retrieval_calls=100,
            max_semantic_calls=100,
            max_patch_calls=100,
        ),
        dossier_id=request.dossier_id,
        source_entry_ref=(f"final:{request.dossier_id}" if request.dossier_id else None),
        initial_graph_json={
            "graph_id": f"ok_tx_{request_id_prefix}",
            "nodes": [],
            "edges": [],
            "metadata": {
                "source": "orchestration_kernel_transcript_edit",
                "dossier_id": request.dossier_id,
            },
        },
    )
    start_result = session_manager.start_session(start_request)
    if start_result.refusal is not None or start_result.session_id is None:
        reason = start_result.refusal.reason_code if start_result.refusal else "missing_session"
        return TranscriptEditAgentRunResult(
            run_artifact_ref=None,
            session_id="",
            iterations=0,
            status="failed",
            reason_code=f"kernel_start_refused:{reason}",
            latest_refs={},
            review_required=True,
        )
    session_id = start_result.session_id
    run_artifact_ref = start_result.run_artifact_ref

    domain_pack = TranscriptEditDomainPack(
        request=request,
        session_id=session_id,
        request_id_prefix=request_id_prefix,
        planner=planner,
        progress_cb=progress_cb,
    )
    kernel_result = run_orchestration_kernel_loop(
        domain_pack=domain_pack,
        session_manager=session_manager,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        request_id_prefix=request_id_prefix,
        dossier_id=request.dossier_id,
        max_iterations=int(request.max_iterations),
        max_no_progress_iterations=int(getattr(request, "max_no_progress_iterations", 3)),
        max_invalid_plan_attempts=int(request.max_invalid_plan_attempts),
        progress_cb=progress_cb,
        resume_hitl_response=resume_feedback_response,
    )

    # Phase 11 D2 / Phase 12 D2: persist the kernel-direct trace and surface its ref.
    trace_artifact_ref = persist_kernel_trace(
        kernel_result=kernel_result,
        request_id_prefix=request_id_prefix,
    )
    enriched_latest_refs = dict(kernel_result.latest_refs)
    if trace_artifact_ref:
        enriched_latest_refs["trace_artifact_ref"] = trace_artifact_ref

    # Merge domain-pack runtime state (has mission_runtime_summary) with kernel loop state.
    domain_state = domain_pack.build_domain_runtime_state()
    kernel_state = kernel_result.domain_runtime_state if isinstance(kernel_result.domain_runtime_state, dict) else {}
    merged_runtime_state = {**kernel_state, **domain_state}
    return _adapt_kernel_loop_result(
        kernel_result,
        runtime_hitl_state=merged_runtime_state,
        latest_refs_override=enriched_latest_refs,
    )





def _adapt_kernel_loop_result(
    result: KernelLoopResult,
    *,
    runtime_hitl_state: dict[str, Any] | None = None,
    latest_refs_override: dict[str, Any] | None = None,
) -> TranscriptEditAgentRunResult:
    """Convert KernelLoopResult → TranscriptEditAgentRunResult.

    Status mapping (TerminalClass → legacy status string):
      completed      → "completed"
      waiting_human  → "waiting_feedback"
      failed         → "failed"
      blocked / waiting_evidence / exhausted → "needs_review"
    """
    tc = result.terminal_class
    if tc == "completed":
        status = "completed"
    elif tc == "waiting_human":
        status = "waiting_feedback"
    elif tc == "failed":
        status = "failed"
    else:
        status = "needs_review"

    review_required = not (status == "completed" and "auto_promote" in (result.reason_code or ""))

    if runtime_hitl_state is None:
        runtime_hitl_state = result.domain_runtime_state if isinstance(result.domain_runtime_state, dict) else {}

    latest_refs = latest_refs_override if latest_refs_override is not None else dict(result.latest_refs)

    return TranscriptEditAgentRunResult(
        run_artifact_ref=result.run_artifact_ref,
        session_id=result.session_id,
        iterations=result.iterations,
        status=status,
        reason_code=result.reason_code,
        latest_refs=latest_refs,
        review_required=review_required,
        runtime_hitl_state=runtime_hitl_state if runtime_hitl_state else None,
    )


def adapt_transcript_edit_run_result(
    result: TranscriptEditAgentRunResult,
) -> tuple[ModeInterpretation, ModeRecommendation]:
    return (
        interpret_transcript_edit_run_result(result),
        recommend_transcript_edit_run_result(result),
    )


def interpret_transcript_edit_run_result(result: TranscriptEditAgentRunResult) -> ModeInterpretation:
    authority = _authority_snapshot(result)
    terminal_result = classify_transcript_edit_terminal(
        status=result.status,
        reason_code=result.reason_code,
        terminal_classification=authority.terminal_classification,
        human_feedback_pending=authority.waiting_feedback,
    )
    return ModeInterpretation(
        summary=f"transcript_edit_cycle:{terminal_result.terminal_class}",
        details={
            "mode": TRANSCRIPT_EDIT_MODE_NAME,
            "status": result.status,
            "terminal_class": terminal_result.terminal_class,
            "reason_code": result.reason_code,
            "iterations": result.iterations,
            "session_id": result.session_id,
            "run_artifact_ref": result.run_artifact_ref,
            "waiting_feedback": authority.waiting_feedback,
            "closure_blocking": authority.closure_blocking,
            "unresolved_closure_count": authority.unresolved_closure_count,
        },
    )


def recommend_transcript_edit_run_result(result: TranscriptEditAgentRunResult) -> ModeRecommendation:
    authority = _authority_snapshot(result)
    terminal_result = classify_transcript_edit_terminal(
        status=result.status,
        reason_code=result.reason_code,
        terminal_classification=authority.terminal_classification,
        human_feedback_pending=authority.waiting_feedback,
    )
    return ModeRecommendation(
        next_step_hint=None,
        terminal=TerminalRecommendation(
            terminal=True,
            terminal_class=terminal_result.terminal_class,
            reason_code=result.reason_code,
        ),
        high_signal_artifact_refs=_collect_high_signal_refs(result),
        blocker_posture=MissionBlockerPostureSummary(
            waiting_human=authority.waiting_feedback,
            open_blocker_count=authority.open_blocker_count,
        ),
        verification_posture=MissionVerificationPostureSummary(
            status=authority.verification_status,
            last_verification_kind=authority.verification_kind,
        ),
        resumability=MissionResumabilitySummary(
            resumable=authority.waiting_feedback,
            resume_reason="waiting_human_feedback" if authority.waiting_feedback else None,
            resume_requirements=(
                [authority.pending_feedback_prompt_id] if authority.pending_feedback_prompt_id else []
            ),
        ),
    )


def _authority_snapshot(result: TranscriptEditAgentRunResult) -> _TranscriptAuthoritySnapshot:
    runtime_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
    summary = (
        dict(runtime_state.get("mission_runtime_summary"))
        if isinstance(runtime_state.get("mission_runtime_summary"), dict)
        else {}
    )
    waiting_feedback = bool(summary.get("waiting_feedback"))
    pending_feedback_prompt_id = str(summary.get("pending_feedback_prompt_id") or "").strip() or None
    open_blocker_count = summary.get("open_blocker_count")
    unresolved_closure_count = int(summary.get("unresolved_closure_count") or 0)
    closure_blocking = bool(summary.get("closure_blocking"))
    verification_status = _normalize_verification_status(summary.get("verification_status"), closure_blocking, unresolved_closure_count)
    verification_kind = str(summary.get("verification_kind") or "").strip() or "transcript_edit_closure_ledger"
    terminal_classification = str(summary.get("terminal_classification") or "").strip() or None

    if not summary:
        waiting_feedback = bool(runtime_state.get("waiting_feedback"))
        pending_feedback_prompt_id = str(runtime_state.get("pending_feedback_prompt_id") or "").strip() or None

    return _TranscriptAuthoritySnapshot(
        waiting_feedback=waiting_feedback,
        pending_feedback_prompt_id=pending_feedback_prompt_id,
        open_blocker_count=int(open_blocker_count) if isinstance(open_blocker_count, int) else None,
        unresolved_closure_count=unresolved_closure_count,
        closure_blocking=closure_blocking,
        verification_status=verification_status,
        verification_kind=verification_kind,
        terminal_classification=terminal_classification,
    )


def _collect_high_signal_refs(result: TranscriptEditAgentRunResult) -> list[str]:
    refs: list[str] = []
    if isinstance(result.run_artifact_ref, str) and result.run_artifact_ref.strip():
        refs.append(result.run_artifact_ref.strip())
    latest_refs = result.latest_refs if isinstance(result.latest_refs, dict) else {}
    for payload in latest_refs.values():
        if isinstance(payload, dict):
            for key in ("artifact_ref", "artifact_path", "ref", "path"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    refs.append(value.strip())
        elif isinstance(payload, str) and payload.strip():
            refs.append(payload.strip())
    deduped: list[str] = []
    for value in refs:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _normalize_verification_status(
    value: Any,
    closure_blocking: bool,
    unresolved_closure_count: int,
) -> str:
    text = str(value or "").strip().lower()
    if text in {"closure_blocking", "closure_partial", "closure_clear"}:
        return text
    if closure_blocking:
        return "closure_blocking"
    if unresolved_closure_count > 0:
        return "closure_partial"
    return "closure_clear"


def _recommend_transition_back_to_deed_to_ir(
    *,
    request: MissionRuntimeRequest,
    recommendation: ModeRecommendation,
    result: TranscriptEditAgentRunResult,
) -> ModeTransitionRecommendation | None:
    if not _metadata_flag(request.metadata, "phase_e_enable_linear_transitions"):
        return None
    if not _metadata_flag(request.metadata, "transcript_edit_transition_to_deed_to_ir"):
        return None
    verification_status = recommendation.verification_posture.status if recommendation.verification_posture else None
    waiting_human = recommendation.blocker_posture.waiting_human if recommendation.blocker_posture else False
    if waiting_human:
        return None
    if verification_status != "closure_clear":
        return None
    return ModeTransitionRecommendation(
        next_mode="deed_to_ir",
        reason="transcript_edit_review_ready_for_deed_resume",
        handed_forward_artifact_refs=_curate_tx_to_deed_handoff_refs(result, recommendation),
        expected_next_work="resume deed_to_ir with transcript-edit validated artifacts",
        resume_note_for_prior_mode="return to transcript_edit only if new closure blockers emerge",
    )


def _curate_tx_to_deed_handoff_refs(
    result: TranscriptEditAgentRunResult,
    recommendation: ModeRecommendation,
) -> list[str]:
    refs: list[str] = []
    latest_refs = result.latest_refs if isinstance(result.latest_refs, dict) else {}
    trace_ref = latest_refs.get("trace_artifact_ref")
    if isinstance(trace_ref, str) and trace_ref.strip():
        refs.append(trace_ref.strip())
    if isinstance(result.run_artifact_ref, str) and result.run_artifact_ref.strip():
        refs.append(result.run_artifact_ref.strip())
    for payload in latest_refs.values():
        if isinstance(payload, dict):
            for key in ("artifact_ref", "artifact_path", "ref", "path"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip() and "transcript" in value.lower():
                    if value.strip() not in refs:
                        refs.append(value.strip())
        elif isinstance(payload, str) and payload.strip() and "transcript" in payload.lower():
            if payload.strip() not in refs:
                refs.append(payload.strip())
    if refs:
        return refs
    return list(recommendation.high_signal_artifact_refs)


def _metadata_flag(metadata: Any, key: str) -> bool:
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get(key))


def _require_transcript_result(context: ModeCycleContext) -> TranscriptEditAgentRunResult:
    result = context.execution_result
    if isinstance(result, TranscriptEditAgentRunResult):
        return result
    raise ValueError("transcript_edit_mode_context_missing_execution_result")
