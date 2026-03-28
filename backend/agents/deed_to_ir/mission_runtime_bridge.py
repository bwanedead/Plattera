from __future__ import annotations

from typing import Callable

from agent_kernel.models import KernelSessionStartRequest, StopReason, TerminalOutcome, TerminalOutcomeKind
from agent_kernel.session import KernelSessionManager
from agents.controller.controller_runtime import ControllerRunResult, NextStepLLMClient
from agents.controller.domain_pack import DeedToIRDomainPack
from harness.mission_runtime.contracts import MissionLedgerView, MissionRuntimeRequest
from harness.orchestration_kernel import KernelLoopResult, run_orchestration_kernel_loop
from harness.tracing.kernel_trace_persistence import persist_kernel_trace, persist_rationale_strip

from . import build_deed_to_ir_domain_pack_bundle
from .mission_mode_adapter import DeedToIRModeAdapter


def build_deed_to_ir_mode_adapter_from_controller_inputs(
    *,
    session_manager: KernelSessionManager,
    llm_client: NextStepLLMClient,
    start_request: KernelSessionStartRequest | None = None,
    start_request_factory: Callable[[MissionRuntimeRequest, MissionLedgerView], KernelSessionStartRequest] | None = None,
    model: str = "gpt-5-mini",
    max_iterations: int = 20,
) -> DeedToIRModeAdapter:
    def _runner(_request: MissionRuntimeRequest, _ledger: MissionLedgerView) -> ControllerRunResult:
        request = start_request_factory(_request, _ledger) if start_request_factory is not None else start_request
        if request is None:
            raise ValueError("deed_to_ir_mode_requires_start_request_or_factory")
        return run_orchestration_kernel_deed_loop(
            session_manager=session_manager,
            llm_client=llm_client,
            start_request=request,
            model=model,
            max_iterations=max_iterations,
        )

    return DeedToIRModeAdapter(runner=_runner)


def run_orchestration_kernel_deed_loop(
    *,
    session_manager: KernelSessionManager,
    llm_client: NextStepLLMClient,
    start_request: KernelSessionStartRequest,
    model: str = "gpt-5-mini",
    max_iterations: int = 20,
    request_id_prefix: str | None = None,
) -> ControllerRunResult:
    prefix = request_id_prefix or start_request.request_id
    started = session_manager.start_session(start_request)

    if started.refusal is not None or started.session_id is None:
        reason = started.refusal.reason_code if started.refusal else "missing_session"
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
    build_deed_to_ir_domain_pack_bundle(domain_pack)

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

    trace_artifact_ref = persist_kernel_trace(
        kernel_result=kernel_result,
        request_id_prefix=prefix,
    )
    rationale_strip_artifact_ref = persist_rationale_strip(
        kernel_result=kernel_result,
        request_id_prefix=prefix,
        source_trace_artifact_ref=trace_artifact_ref,
    )
    domain_state = domain_pack.build_domain_runtime_state()
    return _adapt_kernel_loop_result_to_controller(
        kernel_result,
        domain_state=domain_state,
        trace_artifact_ref=trace_artifact_ref,
        rationale_strip_artifact_ref=rationale_strip_artifact_ref,
    )


def _adapt_kernel_loop_result_to_controller(
    result: KernelLoopResult,
    *,
    domain_state: dict | None = None,
    trace_artifact_ref: str | None = None,
    rationale_strip_artifact_ref: str | None = None,
) -> ControllerRunResult:
    terminal_class = result.terminal_class
    if terminal_class == "completed":
        stop_reason = StopReason.COMPLETED
        outcome_kind = TerminalOutcomeKind.SUCCESS
        success = True
    elif terminal_class == "waiting_human":
        stop_reason = StopReason.NEEDS_USER_CHOICE
        outcome_kind = TerminalOutcomeKind.NEEDS_USER_CHOICE
        success = False
    elif terminal_class == "waiting_evidence":
        stop_reason = StopReason.NEEDS_UPLOAD
        outcome_kind = TerminalOutcomeKind.NEEDS_UPLOAD
        success = False
    elif terminal_class == "blocked":
        stop_reason = StopReason.NEEDS_CAPABILITY
        outcome_kind = TerminalOutcomeKind.FAILED
        success = False
    elif terminal_class == "exhausted":
        stop_reason = StopReason.BUDGET_EXCEEDED
        outcome_kind = TerminalOutcomeKind.FAILED
        success = False
    else:
        stop_reason = StopReason.INTERNAL_ERROR
        outcome_kind = TerminalOutcomeKind.FAILED
        success = False

    terminal = TerminalOutcome(
        terminal_outcome=outcome_kind,
        stop_reason=stop_reason,
        success=success,
        reason_code=result.reason_code,
    )
    state = domain_state if isinstance(domain_state, dict) else {}
    if not state:
        state = result.domain_runtime_state if isinstance(result.domain_runtime_state, dict) else {}

    domain_latest_refs = state.get("latest_refs")
    merged_refs: dict = {}
    if isinstance(domain_latest_refs, dict):
        merged_refs.update(domain_latest_refs)
    merged_refs.update(dict(result.latest_refs))
    if isinstance(trace_artifact_ref, str) and trace_artifact_ref.strip():
        merged_refs["trace_artifact_ref"] = trace_artifact_ref.strip()
    if isinstance(rationale_strip_artifact_ref, str) and rationale_strip_artifact_ref.strip():
        merged_refs["rationale_strip_artifact_ref"] = rationale_strip_artifact_ref.strip()

    last_dashboard = {
        "latest_refs": merged_refs,
        "deed_phase_hint": state.get("deed_phase_hint"),
        "claimability": state.get("claimability"),
        "failure_classification": state.get("failure_classification"),
    }
    handoff_posture = state.get("handoff_posture")
    return ControllerRunResult(
        terminal=terminal,
        last_dashboard=last_dashboard,
        transcript_artifact_ref=result.run_artifact_ref or "",
        session_id=result.session_id,
        run_artifact_ref=result.run_artifact_ref,
        iterations=result.iterations,
        handoff_posture=handoff_posture if isinstance(handoff_posture, dict) else None,
    )
