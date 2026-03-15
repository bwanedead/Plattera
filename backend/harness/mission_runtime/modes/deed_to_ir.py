from __future__ import annotations

from typing import Any, Callable, Protocol

from agent_kernel.models import (
    KernelBudgets,
    KernelGoal,
    KernelSessionStartRequest,
    KernelSessionStartResult,
    StopReason,
    TerminalOutcome,
    TerminalOutcomeKind,
)
from agent_kernel.session import KernelSessionManager
from agents.controller.controller_runtime import (
    ControllerRunResult,
    IterationDigestClient,
    NextStepLLMClient,
    run_controller_loop,
)
from agents.controller.domain_pack import DeedToIRDomainPack
from harness.orchestration_kernel import run_orchestration_kernel_loop, KernelLoopResult
from harness.tracing.kernel_trace_persistence import persist_kernel_trace

from ...terminal_taxonomy import classify_controller_terminal
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

DEED_TO_IR_MODE_NAME = "deed_to_ir"


class ControllerLoopRunner(Protocol):
    def __call__(
        self,
        *,
        session_manager: KernelSessionManager,
        llm_client: NextStepLLMClient,
        start_request: KernelSessionStartRequest,
        model: str = "gpt-5-mini",
        max_iterations: int = 20,
        digest_client: IterationDigestClient | None = None,
    ) -> ControllerRunResult: ...


class DeedToIRModePolicy(ModePolicy):
    """MissionRuntime ModePolicy adapter for deed-to-IR controller runtime."""

    mode_name = DEED_TO_IR_MODE_NAME

    def __init__(
        self,
        *,
        runner: Callable[[MissionRuntimeRequest, MissionLedgerView], ControllerRunResult],
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
            # Runtime executes this adapter mechanically before interpretation.
            execution_adapter=lambda: self._runner(request, ledger),
        )

    def interpret(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
    ) -> ModeInterpretation:
        return interpret_controller_run_result(_require_controller_result(context))

    def recommend(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
        interpretation: ModeInterpretation,
    ) -> ModeRecommendation:
        result = _require_controller_result(context)
        recommendation = recommend_controller_run_result(result)
        transition = _recommend_transition_to_transcript_edit(
            request=request,
            recommendation=recommendation,
        )
        if transition is None:
            return recommendation
        return ModeRecommendation(
            next_step_hint="handoff_to_transcript_edit",
            transition=transition,
            terminal=recommendation.terminal,
            high_signal_artifact_refs=list(recommendation.high_signal_artifact_refs),
            blocker_posture=recommendation.blocker_posture,
            verification_posture=recommendation.verification_posture,
            resumability=recommendation.resumability,
        )


def build_deed_to_ir_mode_policy_from_controller_inputs(
    *,
    session_manager: KernelSessionManager,
    llm_client: NextStepLLMClient,
    start_request: KernelSessionStartRequest,
    model: str = "gpt-5-mini",
    max_iterations: int = 20,
    digest_client: IterationDigestClient | None = None,
    controller_runner: ControllerLoopRunner = run_controller_loop,
    use_orchestration_kernel: bool = False,
) -> DeedToIRModePolicy:
    """Build a deed-to-IR ModePolicy backed by controller runtime or orchestration kernel."""

    def _runner(_request: MissionRuntimeRequest, _ledger: MissionLedgerView) -> ControllerRunResult:
        if use_orchestration_kernel:
            return run_orchestration_kernel_deed_loop(
                session_manager=session_manager,
                llm_client=llm_client,
                start_request=start_request,
                model=model,
                max_iterations=max_iterations,
            )
        return controller_runner(
            session_manager=session_manager,
            llm_client=llm_client,
            start_request=start_request,
            model=model,
            max_iterations=max_iterations,
            digest_client=digest_client,
        )

    return DeedToIRModePolicy(runner=_runner)


# ---------------------------------------------------------------------------
# Orchestration kernel runner + adapter
# ---------------------------------------------------------------------------


def run_orchestration_kernel_deed_loop(
    *,
    session_manager: KernelSessionManager,
    llm_client: NextStepLLMClient,
    start_request: KernelSessionStartRequest,
    model: str = "gpt-5-mini",
    max_iterations: int = 20,
    request_id_prefix: str | None = None,
) -> ControllerRunResult:
    """Run deed-to-IR through the orchestration kernel and adapt the result.

    Calls start_session, creates DeedToIRDomainPack, runs the kernel loop,
    and adapts KernelLoopResult → ControllerRunResult.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    prefix = request_id_prefix or start_request.request_id
    started = session_manager.start_session(start_request)

    if started.refusal is not None or started.session_id is None:
        reason = started.refusal.reason_code if started.refusal else "missing_session"
        _log.warning("DEED_OK start_session_refused ► reason=%s", reason)
        terminal = TerminalOutcome(
            terminal_outcome=TerminalOutcomeKind.FAILED,
            stop_reason=StopReason.INTERNAL_ERROR,
            success=False,
            reason_code=f"kernel_start_refused:{reason}",
        )
        return ControllerRunResult(
            terminal=terminal,
            last_dashboard={},
            transcript_artifact_ref="",
            session_id=None,
            run_artifact_ref=None,
            iterations=0,
        )

    session_id = started.session_id
    run_artifact_ref = started.run_artifact_ref

    domain_pack = DeedToIRDomainPack(
        start_request=start_request,
        started=started,
        model=model,
        llm_client=llm_client,
        request_id_prefix=prefix,
    )

    max_no_progress = max(3, max_iterations // 4)
    kernel_result = run_orchestration_kernel_loop(
        domain_pack=domain_pack,
        session_manager=session_manager,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        request_id_prefix=prefix,
        dossier_id=start_request.dossier_id,
        max_iterations=max_iterations,
        max_no_progress_iterations=max_no_progress,
        max_invalid_plan_attempts=3,
    )

    # Phase 12 D1: persist kernel-direct trace and surface ref (parity with transcript).
    trace_artifact_ref = persist_kernel_trace(
        kernel_result=kernel_result,
        request_id_prefix=prefix,
    )

    # D3 — merge domain pack's accumulated refs (all steps) with kernel's latest_refs
    # (only the final step). domain_pack._latest_refs accumulates via hook 7 merge and
    # survives step boundaries; kernel loop_memory.latest_refs is replaced each step.
    domain_state = domain_pack.build_domain_runtime_state()
    return _adapt_kernel_loop_result_to_controller(
        kernel_result,
        domain_state=domain_state,
        trace_artifact_ref=trace_artifact_ref,
    )


def _adapt_kernel_loop_result_to_controller(
    result: KernelLoopResult,
    *,
    domain_state: dict | None = None,
    trace_artifact_ref: str | None = None,
) -> ControllerRunResult:
    """Convert KernelLoopResult → ControllerRunResult.

    TerminalClass mapping:
      completed      → success=True, COMPLETED / SUCCESS
      waiting_human  → NEEDS_USER_CHOICE / NEEDS_USER_CHOICE
      waiting_evidence → NEEDS_UPLOAD / NEEDS_UPLOAD
      blocked        → NEEDS_CAPABILITY / FAILED
      exhausted      → BUDGET_EXCEEDED / FAILED
      failed         → INTERNAL_ERROR / FAILED
    """
    tc = result.terminal_class
    if tc == "completed":
        stop_reason = StopReason.COMPLETED
        outcome_kind = TerminalOutcomeKind.SUCCESS
        success = True
    elif tc == "waiting_human":
        stop_reason = StopReason.NEEDS_USER_CHOICE
        outcome_kind = TerminalOutcomeKind.NEEDS_USER_CHOICE
        success = False
    elif tc == "waiting_evidence":
        stop_reason = StopReason.NEEDS_UPLOAD
        outcome_kind = TerminalOutcomeKind.NEEDS_UPLOAD
        success = False
    elif tc == "blocked":
        stop_reason = StopReason.NEEDS_CAPABILITY
        outcome_kind = TerminalOutcomeKind.FAILED
        success = False
    elif tc == "exhausted":
        stop_reason = StopReason.BUDGET_EXCEEDED
        outcome_kind = TerminalOutcomeKind.FAILED
        success = False
    else:  # failed
        stop_reason = StopReason.INTERNAL_ERROR
        outcome_kind = TerminalOutcomeKind.FAILED
        success = False

    terminal = TerminalOutcome(
        terminal_outcome=outcome_kind,
        stop_reason=stop_reason,
        success=success,
        reason_code=result.reason_code,
    )
    _domain_state = domain_state if isinstance(domain_state, dict) else {}
    if not _domain_state:
        _domain_state = result.domain_runtime_state if isinstance(result.domain_runtime_state, dict) else {}

    # D3 — merge domain pack's accumulated refs (base) with kernel's final latest_refs
    # (authoritative for the last executed step). Domain pack refs survive all steps;
    # kernel refs reflect only the most recent step replacement.
    domain_latest_refs = _domain_state.get("latest_refs")
    merged_refs: dict = {}
    if isinstance(domain_latest_refs, dict):
        merged_refs.update(domain_latest_refs)
    merged_refs.update(dict(result.latest_refs))
    # Phase 12 D1: surface trace artifact ref so high_signal_refs can include it.
    if isinstance(trace_artifact_ref, str) and trace_artifact_ref.strip():
        merged_refs["trace_artifact_ref"] = trace_artifact_ref.strip()

    last_dashboard = {
        "latest_refs": merged_refs,
        "deed_phase_hint": _domain_state.get("deed_phase_hint"),
        "claimability": _domain_state.get("claimability"),
        "failure_classification": _domain_state.get("failure_classification"),
    }
    return ControllerRunResult(
        terminal=terminal,
        last_dashboard=last_dashboard,
        transcript_artifact_ref=result.run_artifact_ref or "",
        session_id=result.session_id,
        run_artifact_ref=result.run_artifact_ref,
        iterations=result.iterations,
    )


def adapt_controller_run_result(result: ControllerRunResult) -> tuple[ModeInterpretation, ModeRecommendation]:
    return (
        interpret_controller_run_result(result),
        recommend_controller_run_result(result),
    )


def interpret_controller_run_result(result: ControllerRunResult) -> ModeInterpretation:
    terminal_result = classify_controller_terminal(
        stop_reason=result.terminal.stop_reason.value,
        terminal_outcome=result.terminal.terminal_outcome.value,
        success=result.terminal.success,
        reason_code=result.terminal.reason_code,
    )
    return ModeInterpretation(
        summary=f"deed_to_ir_cycle:{terminal_result.terminal_class}",
        details={
            "mode": DEED_TO_IR_MODE_NAME,
            "terminal_class": terminal_result.terminal_class,
            "reason_code": terminal_result.reason_code,
            "iterations": result.iterations,
            "session_id": result.session_id,
            "run_artifact_ref": result.run_artifact_ref,
            "transcript_artifact_ref": result.transcript_artifact_ref,
        },
    )


def recommend_controller_run_result(result: ControllerRunResult) -> ModeRecommendation:
    terminal_result = classify_controller_terminal(
        stop_reason=result.terminal.stop_reason.value,
        terminal_outcome=result.terminal.terminal_outcome.value,
        success=result.terminal.success,
        reason_code=result.terminal.reason_code,
    )
    waiting = terminal_result.terminal_class in {"waiting_human", "waiting_evidence"}
    return ModeRecommendation(
        next_step_hint=None,
        terminal=TerminalRecommendation(
            terminal=True,
            terminal_class=terminal_result.terminal_class,
            reason_code=terminal_result.reason_code,
        ),
        high_signal_artifact_refs=_collect_high_signal_refs(result),
        blocker_posture=MissionBlockerPostureSummary(waiting_human=terminal_result.terminal_class == "waiting_human"),
        verification_posture=MissionVerificationPostureSummary(
            status=result.terminal.stop_reason.value or terminal_result.reason_code,
            last_verification_kind="controller_terminal",
        ),
        resumability=MissionResumabilitySummary(
            resumable=waiting,
            resume_reason=terminal_result.terminal_class if waiting else None,
        ),
    )


def _collect_high_signal_refs(result: ControllerRunResult) -> list[str]:
    refs: list[str] = []
    for candidate in [result.run_artifact_ref, result.transcript_artifact_ref]:
        if isinstance(candidate, str) and candidate.strip():
            refs.append(candidate.strip())
    latest_refs = result.last_dashboard.get("latest_refs") if isinstance(result.last_dashboard, dict) else None
    if isinstance(latest_refs, dict):
        for payload in latest_refs.values():
            if isinstance(payload, dict):
                for key in ("artifact_ref", "artifact_path", "ref", "path"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        refs.append(value.strip())
            elif isinstance(payload, str) and payload.strip():
                # Top-level string refs (e.g. trace_artifact_ref) surfaced directly.
                refs.append(payload.strip())
    deduped: list[str] = []
    for value in refs:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _recommend_transition_to_transcript_edit(
    *,
    request: MissionRuntimeRequest,
    recommendation: ModeRecommendation,
) -> ModeTransitionRecommendation | None:
    if not _metadata_flag(request.metadata, "phase_e_enable_linear_transitions"):
        return None
    if not _metadata_flag(request.metadata, "deed_to_ir_transition_to_transcript_edit"):
        return None
    terminal_class = recommendation.terminal.terminal_class if recommendation.terminal is not None else None
    if terminal_class != "completed":
        return None
    return ModeTransitionRecommendation(
        next_mode="transcript_edit",
        reason="deed_to_ir_output_requires_transcript_edit_review",
        handed_forward_artifact_refs=list(recommendation.high_signal_artifact_refs),
        expected_next_work="run transcript-edit pass over latest deed output and verify closure posture",
        resume_note_for_prior_mode="resume deed_to_ir after transcript-edit returns reconciled artifacts",
    )


def _metadata_flag(metadata: Any, key: str) -> bool:
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get(key))


def _require_controller_result(context: ModeCycleContext) -> ControllerRunResult:
    result = context.execution_result
    if isinstance(result, ControllerRunResult):
        return result
    raise ValueError("deed_to_ir_mode_context_missing_execution_result")
