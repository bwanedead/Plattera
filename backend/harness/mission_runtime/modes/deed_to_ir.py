from __future__ import annotations

from typing import Any, Callable, Protocol

from agent_kernel.models import KernelSessionStartRequest
from agent_kernel.session import KernelSessionManager
from agents.controller.controller_runtime import (
    ControllerRunResult,
    IterationDigestClient,
    NextStepLLMClient,
    run_controller_loop,
)

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
) -> DeedToIRModePolicy:
    """Build a deed-to-IR ModePolicy backed by existing controller runtime."""

    def _runner(_request: MissionRuntimeRequest, _ledger: MissionLedgerView) -> ControllerRunResult:
        return controller_runner(
            session_manager=session_manager,
            llm_client=llm_client,
            start_request=start_request,
            model=model,
            max_iterations=max_iterations,
            digest_client=digest_client,
        )

    return DeedToIRModePolicy(runner=_runner)


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
