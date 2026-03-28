from __future__ import annotations

from typing import Any, Callable

from agent_kernel.models import StopReason, TerminalOutcomeKind
from agents.controller.controller_runtime import ControllerRunResult
from harness.mission_runtime.contracts import (
    MissionBlockerPostureSummary,
    MissionLedgerView,
    MissionModeAdapter,
    MissionModeRunEnvelope,
    MissionResumabilitySummary,
    MissionRuntimeRequest,
    MissionVerificationPostureSummary,
    ModeCycleContext,
    ModeInterpretation,
    ModeRecommendation,
    TerminalRecommendation,
)
from harness.mission_runtime.mapping_family import build_mapping_family_coordination
from harness.terminal_taxonomy import classify_controller_terminal

DEED_TO_IR_MODE_NAME = "deed_to_ir"


class DeedToIRModeAdapter(MissionModeAdapter):
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
            execution_adapter=lambda: self._runner(request, ledger),
        )

    def build_run_envelope(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
    ) -> MissionModeRunEnvelope:
        result = _require_controller_result(context)
        interpretation, recommendation = adapt_controller_run_result(result)
        coordination = build_mapping_family_coordination(
            current_mode=DEED_TO_IR_MODE_NAME,
            handoff_posture=result.handoff_posture,
            terminal=recommendation.terminal,
            transition_allowed=_metadata_flag(request.metadata, "phase_e_enable_linear_transitions")
            and _metadata_flag(request.metadata, "deed_to_ir_transition_to_transcript_edit"),
            handed_forward_artifact_refs=_curate_deed_to_tx_handoff_refs(result, recommendation),
            resume_note_for_prior_mode="resume deed_to_ir after transcript-edit returns reconciled artifacts",
        )
        return MissionModeRunEnvelope(
            summary=interpretation.summary,
            high_signal_artifact_refs=tuple(recommendation.high_signal_artifact_refs),
            blocker_posture=recommendation.blocker_posture,
            verification_posture=recommendation.verification_posture,
            resumability=recommendation.resumability,
            terminal=recommendation.terminal,
            transition=coordination.transition_recommendation,
            family_coordination=coordination,
            domain_payload={
                "mode": DEED_TO_IR_MODE_NAME,
                "terminal_outcome": result.terminal.terminal_outcome.value,
                "stop_reason": result.terminal.stop_reason.value,
                "reason_code": result.terminal.reason_code,
                "iterations": result.iterations,
                "session_id": result.session_id,
                "run_artifact_ref": result.run_artifact_ref,
                "transcript_artifact_ref": result.transcript_artifact_ref,
                "latest_refs": dict(result.last_dashboard.get("latest_refs") or {}),
                **(
                    {"handoff_posture": dict(result.handoff_posture)}
                    if isinstance(result.handoff_posture, dict)
                    else {}
                ),
            },
        )

    def interpret(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
    ) -> ModeInterpretation:
        del request
        del ledger
        envelope = _require_controller_run_envelope(context)
        return ModeInterpretation(summary=envelope.summary, details=dict(envelope.domain_payload))

    def recommend(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
        interpretation: ModeInterpretation,
    ) -> ModeRecommendation:
        del request
        del ledger
        del interpretation
        envelope = _require_controller_run_envelope(context)
        recommendation = ModeRecommendation(
            terminal=envelope.terminal,
            high_signal_artifact_refs=list(envelope.high_signal_artifact_refs),
            blocker_posture=envelope.blocker_posture,
            verification_posture=envelope.verification_posture,
            resumability=envelope.resumability,
        )
        if envelope.transition is None:
            return recommendation
        return ModeRecommendation(
            transition=envelope.transition,
            terminal=recommendation.terminal,
            high_signal_artifact_refs=list(recommendation.high_signal_artifact_refs),
            blocker_posture=recommendation.blocker_posture,
            verification_posture=recommendation.verification_posture,
            resumability=recommendation.resumability,
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
                refs.append(payload.strip())
    deduped: list[str] = []
    for value in refs:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _curate_deed_to_tx_handoff_refs(
    result: ControllerRunResult,
    recommendation: ModeRecommendation,
) -> list[str]:
    refs: list[str] = []
    latest_refs = result.last_dashboard.get("latest_refs") if isinstance(result.last_dashboard, dict) else {}
    if isinstance(latest_refs, dict):
        trace_ref = latest_refs.get("trace_artifact_ref")
        if isinstance(trace_ref, str) and trace_ref.strip():
            refs.append(trace_ref.strip())
    if isinstance(result.transcript_artifact_ref, str) and result.transcript_artifact_ref.strip():
        refs.append(result.transcript_artifact_ref.strip())
    if isinstance(result.run_artifact_ref, str) and result.run_artifact_ref.strip():
        refs.append(result.run_artifact_ref.strip())
    if refs:
        deduped: list[str] = []
        for value in refs:
            if value not in deduped:
                deduped.append(value)
        return deduped
    return list(recommendation.high_signal_artifact_refs)


def _metadata_flag(metadata: Any, key: str) -> bool:
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get(key))


def _require_controller_result(context: ModeCycleContext) -> ControllerRunResult:
    result = context.execution_result
    if isinstance(result, ControllerRunResult):
        return result
    raise ValueError("deed_to_ir_mode_context_missing_execution_result")


def _require_controller_run_envelope(context: ModeCycleContext) -> MissionModeRunEnvelope:
    envelope = context.run_envelope
    if isinstance(envelope, MissionModeRunEnvelope):
        return envelope
    raise ValueError("deed_to_ir_mode_context_missing_run_envelope")
